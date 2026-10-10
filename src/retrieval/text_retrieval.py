"""C 模块（检索）适配层：只加载官方 Web 索引 + BGE 编码器。

设计约束（来自 m3.v1 协议与 C 的任务书）：
  * **只做文本检索**。绝不初始化官方 ``UnifiedSearchPipeline`` 的 CLIP 图像分支，
    也绝不读取图片、图片 URL、OCR、caption、视觉实体、``full_query``、对话历史
    或参考答案。输入只有原始 query 字符串。
  * 索引与编码器 revision 必须不可变且可记录。
  * 命中整理成 m3.v1 的 ``hits`` 结构；``text`` 必填，缺正文时按协议
    （"text来自真实官方返回的标题/片段内容"）回退到标题，两者皆空则丢弃该命中。
  * **不做**重排、实时网页抓取、答案建库。

本模块不在 import 时加载 torch / chromadb，保证 ``--help`` 不下载索引、不加载模型。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 官方包 0.5.1 里固定的集合名（见 cragmm_search/web_search_mock_api/api/web_search.py）
COLLECTION_NAME = "web_search_embeddings"

# m3.v1 hit.score_kind 允许的取值
SCORE_KINDS = ("similarity", "distance", "unknown")


class RetrievalError(RuntimeError):
    """检索层的技术故障基类。调用方据此写 retrieval_status="error"。"""


class ConfigError(ValueError):
    """配置本身不合法，属于结构性错误，不应产出正式结果。"""


class IndexUnavailableError(RetrievalError):
    """索引无法打开。"""


class EncoderUnavailableError(RetrievalError):
    """编码器无法加载或推理失败。"""


# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------

_DEFAULTS: dict[str, Any] = {
    "top_k": 5,
    "collection_name": COLLECTION_NAME,
    "hnsw_space_expected": "cosine",
    "score_kind": "similarity",
    "max_length": 512,
    "pooling": "mean",
    "normalize": True,
    "query_prefix": "",
    "device": "auto",
    "dedupe_by_chunk_prefix": True,
    "rerank": False,
    "live_web_fetch": False,
    "retry_max": 3,
}


@dataclass(frozen=True)
class RetrievalConfig:
    """从配置字典解析出的、经过校验的检索设置。"""

    raw: dict[str, Any]
    top_k: int
    index_repo: str
    index_revision: str
    encoder_id: str
    encoder_revision: str
    collection_name: str
    hnsw_space_expected: str
    score_kind: str
    max_length: int
    pooling: str
    normalize: bool
    query_prefix: str
    device: str
    dedupe_by_chunk_prefix: bool
    retry_max: int
    index_cache_dir: str | None

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> "RetrievalConfig":
        if not isinstance(config, dict):
            raise ConfigError("retrieval config must be a JSON object")
        if "fetch_k" in config:
            raise ConfigError(
                "fetch_k is not implemented; top_k controls the raw chunk query "
                "and the final page cap. Remove fetch_k instead of silently ignoring it."
            )
        merged = {**_DEFAULTS, **config}

        for key in ("index_repo", "index_revision", "encoder_id", "encoder_revision"):
            value = merged.get(key)
            if not isinstance(value, str) or not value.strip():
                raise ConfigError(f"config.{key} must be a nonempty string")
        for key in ("index_revision", "encoder_revision"):
            if merged[key].strip().lower() in {"main", "master", "latest", "head"}:
                raise ConfigError(f"config.{key} must be an immutable revision, not a moving ref")
        if "top_k" not in config or type(config["top_k"]) is not int or config["top_k"] < 1:
            raise ConfigError("config.top_k must be a positive integer")
        if merged["pooling"] != "mean":
            # 官方 0.5.1 用的是 attention-mask 加权的 mean pooling，其它取值属语义漂移
            raise ConfigError("only pooling='mean' matches the official 0.5.1 semantics")
        if not isinstance(merged["normalize"], bool) or not merged["normalize"]:
            raise ConfigError("only normalize=true matches the official 0.5.1 semantics")
        if merged["rerank"]:
            raise ConfigError("M3 C 不做重排")
        if merged["live_web_fetch"]:
            raise ConfigError("M3 C 不抓取实时网页，也不得用实时搜索替代官方索引")
        if not isinstance(merged["max_length"], int) or merged["max_length"] < 1:
            raise ConfigError("config.max_length must be a positive integer")
        if merged["score_kind"] not in SCORE_KINDS:
            raise ConfigError(f"config.score_kind must be one of {SCORE_KINDS}")
        if not isinstance(merged["retry_max"], int) or merged["retry_max"] < 0:
            raise ConfigError("config.retry_max must be a nonnegative integer")

        return cls(
            raw=dict(config),
            top_k=merged["top_k"],
            index_repo=merged["index_repo"].strip(),
            index_revision=merged["index_revision"].strip(),
            encoder_id=merged["encoder_id"].strip(),
            encoder_revision=merged["encoder_revision"].strip(),
            collection_name=merged["collection_name"],
            hnsw_space_expected=merged["hnsw_space_expected"],
            score_kind=merged["score_kind"],
            max_length=merged["max_length"],
            pooling=merged["pooling"],
            normalize=merged["normalize"],
            query_prefix=merged["query_prefix"],
            device=merged["device"],
            dedupe_by_chunk_prefix=bool(merged["dedupe_by_chunk_prefix"]),
            retry_max=merged["retry_max"],
            index_cache_dir=merged.get("index_cache_dir"),
        )


# --------------------------------------------------------------------------
# 命中
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchHit:
    rank: int
    doc_id: str
    url: str | None
    title: str
    text: str
    score: float | None
    score_kind: str

    def to_m3(self) -> dict[str, Any]:
        """转成 接口字段.schema.json 的 hit 定义（字段必须完全一致，additionalProperties=false）。"""
        return {
            "rank": self.rank,
            "doc_id": self.doc_id,
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "score": self.score,
            "score_kind": self.score_kind,
        }


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else ("" if value is None else str(value))


def build_hits(
    ids: list[str],
    distances: list[float] | None,
    metadatas: list[dict[str, Any]] | None,
    config: RetrievalConfig,
) -> list[SearchHit]:
    """把 Chroma 的查询结果整理成 m3.v1 的 hits。

    ``score`` 的语义：官方 0.5.1 用 ``score = 1.0 - distance``。本函数沿用该公式，
    但 ``score_kind`` 由调用方依据集合的真实距离空间决定（见 ``WebTextRetriever``）。
    """
    hits: list[SearchHit] = []
    metas = metadatas or [{} for _ in ids]
    dists = distances if distances is not None else [None] * len(ids)  # type: ignore[list-item]

    for doc_id, distance, meta in zip(ids, dists, metas):
        meta = meta or {}
        title = _as_text(meta.get("page_name"))
        snippet = _as_text(meta.get("page_snippet"))
        # 协议允许 text 取自"标题/片段内容"；schema 要求 text 非空，故先片段后标题
        text = snippet.strip() or title.strip()
        if not text:
            # 既无正文也无标题 → 无法构成合规命中，丢弃并计数（不伪造内容）
            continue
        raw_url = meta.get("page_url")
        url = _as_text(raw_url) or None
        score = None if distance is None else float(1.0) - float(distance)
        hits.append(
            SearchHit(
                rank=len(hits) + 1,
                doc_id=_as_text(doc_id),
                url=url,
                title=title,
                text=text,
                score=score,
                score_kind=config.score_kind,
            )
        )
    return hits


def dedupe_by_chunk(ids: list[str], distances: list[float], metadatas: list[dict[str, Any]]):
    """按 ``doc_id.split("_chunk")[0]`` 去重，保留每组里距离最小的那条。

    这是官方 ``web_search`` 的行为：**先去重再截断**，因此最终条数可能少于 top_k。
    """
    best: dict[str, int] = {}
    for position, doc_id in enumerate(ids):
        base = doc_id.split("_chunk")[0] if "_chunk" in doc_id else doc_id
        current = best.get(base)
        if current is None or distances[position] < distances[current]:
            best[base] = position
    order = sorted(best.values(), key=lambda position: distances[position])
    return (
        [ids[position] for position in order],
        [distances[position] for position in order],
        [metadatas[position] for position in order],
    )


# --------------------------------------------------------------------------
# 索引定位
# --------------------------------------------------------------------------


def resolve_index_path(config: RetrievalConfig, override: str | Path | None = None) -> Path:
    """返回**可写**的索引目录。

    优先级：显式 override > ``config.index_cache_dir`` > HF 缓存快照。

    注意：Chroma 打开集合时会写 ``chroma.sqlite3``，所以直接把 HF 缓存快照交给它
    会破坏那份已校验的字节。调用方应优先给 ``index_cache_dir``（工作副本）。
    """
    if override is not None:
        path = Path(override).expanduser()
        if not path.is_dir():
            raise IndexUnavailableError(f"--index-path 不是目录: {path}")
        return path

    if config.index_cache_dir:
        path = Path(config.index_cache_dir).expanduser()
        if path.is_dir():
            return path
        raise IndexUnavailableError(
            f"config.index_cache_dir 不存在: {path}；"
            "请先给一份可写工作副本，或用 --index-path 指定"
        )

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover
        raise IndexUnavailableError("未安装 huggingface_hub，无法下载索引") from exc

    try:
        resolved = snapshot_download(
            repo_id=config.index_repo,
            repo_type="dataset",
            revision=config.index_revision,
        )
    except Exception as exc:
        raise IndexUnavailableError(f"索引下载失败: {type(exc).__name__}") from exc
    return Path(resolved)


def prepare_working_copy(config: RetrievalConfig, dest: str | Path, *, overwrite: bool = False) -> Path:
    """把固定 revision 的 HF 快照复制成一份可写工作副本（一次性操作）。

    这样做是为了让 HF 缓存里那份经过 SHA256 校验的字节保持原样。
    """
    import shutil

    destination = Path(dest).expanduser()
    if destination.exists():
        if not overwrite:
            raise ConfigError(f"目标已存在，拒绝覆盖: {destination}（如需重建请显式 --overwrite）")
        shutil.rmtree(destination)

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover
        raise IndexUnavailableError("未安装 huggingface_hub，无法定位索引快照") from exc

    source = Path(
        snapshot_download(
            repo_id=config.index_repo,
            repo_type="dataset",
            revision=config.index_revision,
        )
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    return destination


# --------------------------------------------------------------------------
# 检索器
# --------------------------------------------------------------------------


class WebTextRetriever:
    """只加载 Chroma Web 索引 + BGE 编码器的检索器。"""

    def __init__(self, config: RetrievalConfig, index_path: Path, device: str | None = None):
        self.config = config
        self.index_path = Path(index_path)
        self._device_override = device
        self._model = None
        self._tokenizer = None
        self._collection = None
        self._torch = None
        self._device = None
        self.observed_space: str | None = None

    # -- 生命周期 ---------------------------------------------------------

    def load(self) -> None:
        """打开集合并加载编码器。失败抛 IndexUnavailableError / EncoderUnavailableError。"""
        self._load_index()
        self._load_encoder()

    def close(self) -> None:
        self._model = None
        self._tokenizer = None
        self._collection = None
        try:
            if self._torch is not None and self._torch.cuda.is_available():
                self._torch.cuda.empty_cache()
        except Exception:
            pass

    def __enter__(self) -> "WebTextRetriever":
        self.load()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- 内部 -------------------------------------------------------------

    def _load_index(self) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise IndexUnavailableError("未安装 chromadb") from exc

        try:
            client = chromadb.PersistentClient(path=str(self.index_path))
            self._collection = client.get_collection(name=self.config.collection_name)
        except Exception as exc:
            raise IndexUnavailableError(
                f"打开集合 {self.config.collection_name!r} 失败: {type(exc).__name__}"
            ) from exc

        # 记录真实距离空间：它决定 score = 1 - distance 的物理含义，进而决定 score_kind
        self.observed_space = self._read_space(self._collection)
        if self.observed_space and self.config.hnsw_space_expected:
            if self.observed_space != self.config.hnsw_space_expected:
                raise IndexUnavailableError(
                    "集合距离空间与配置不符："
                    f"observed={self.observed_space!r} expected={self.config.hnsw_space_expected!r}；"
                    "score_kind 可能被误标，拒绝继续"
                )

    @staticmethod
    def _read_space(collection: Any) -> str | None:
        try:
            configuration = collection.configuration
            if isinstance(configuration, dict):
                hnsw = configuration.get("hnsw")
                if isinstance(hnsw, dict) and isinstance(hnsw.get("space"), str):
                    return hnsw["space"]
        except Exception:
            pass
        try:
            metadata = collection.metadata
            if isinstance(metadata, dict) and isinstance(metadata.get("hnsw:space"), str):
                return metadata["hnsw:space"]
        except Exception:
            pass
        return None

    def _load_encoder(self) -> None:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise EncoderUnavailableError("未安装 torch / transformers") from exc

        self._torch = torch
        device = self._device_override or self.config.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self._device = torch.device(device)

        try:
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.config.encoder_id, revision=self.config.encoder_revision
            )
            self._model = (
                AutoModel.from_pretrained(
                    self.config.encoder_id, revision=self.config.encoder_revision
                )
                .to(self._device)
                .eval()
            )
        except Exception as exc:
            raise EncoderUnavailableError(
                f"加载编码器 {self.config.encoder_id!r} 失败: {type(exc).__name__}"
            ) from exc

    @staticmethod
    def _mean_pooling(token_embeddings: Any, attention_mask: Any) -> Any:
        expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        import torch

        return torch.sum(token_embeddings * expanded, 1) / torch.clamp(expanded.sum(1), min=1e-9)

    def encode(self, query: str) -> Any:
        """按官方 0.5.1 的配方编码 query：max_length=512、mean pooling、L2 归一化。"""
        if self._model is None or self._tokenizer is None:
            raise EncoderUnavailableError("编码器尚未加载")
        torch = self._torch
        text = f"{self.config.query_prefix}{query}"
        try:
            inputs = self._tokenizer(
                [text],
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=self.config.max_length,
            )
            inputs = {key: value.to(self._device) for key, value in inputs.items()}
            with torch.no_grad():
                outputs = self._model(**inputs)
                features = self._mean_pooling(outputs.last_hidden_state, inputs["attention_mask"])
            features = features / features.norm(dim=-1, keepdim=True)
            return features.cpu().numpy()
        except RetrievalError:
            raise
        except Exception as exc:
            raise EncoderUnavailableError(f"编码失败: {type(exc).__name__}") from exc

    # -- 对外 -------------------------------------------------------------

    def search(self, query: str) -> list[SearchHit]:
        """对**原始 query** 检索，返回按官方语义整理的 hits（可能为空）。

        只接受一个字符串参数：调用方无法从这里传入图片、历史或参考答案。
        """
        if not isinstance(query, str) or not query.strip():
            raise RetrievalError("query 必须是非空字符串")
        if self._collection is None:
            raise IndexUnavailableError("索引尚未打开")

        embedding = self.encode(query)
        try:
            result = self._collection.query(
                query_embeddings=embedding.reshape(1, -1).tolist(),
                n_results=self.config.top_k,
            )
        except Exception as exc:
            raise RetrievalError(f"查询索引失败: {type(exc).__name__}") from exc

        ids = list(result.get("ids", [[]])[0])
        if not ids:
            return []
        distances = list(result["distances"][0]) if result.get("distances") else None
        metadatas = list(result["metadatas"][0]) if result.get("metadatas") else None

        if distances is not None and self.config.dedupe_by_chunk_prefix:
            ids, distances, metadatas = dedupe_by_chunk(
                ids, distances, metadatas or [{} for _ in ids]
            )
        if distances is None:
            return build_hits(ids, None, metadatas, self.config)
        return build_hits(ids[: self.config.top_k], distances[: self.config.top_k],
                          (metadatas or [{} for _ in ids])[: self.config.top_k], self.config)

    @property
    def index_revision(self) -> str:
        return self.config.index_revision

    @property
    def encoder_revision(self) -> str:
        return self.config.encoder_revision

    @property
    def device(self) -> str:
        return str(self._device) if self._device is not None else "unloaded"
