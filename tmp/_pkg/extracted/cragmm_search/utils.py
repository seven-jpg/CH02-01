from typing import Any

import chromadb
import numpy as np
import os
import hashlib
import json
import lmdb

def add_embeddings_to_collection(
    collection, all_embeddings, max_batch_size=5000
) -> chromadb.Collection:
    # Note - Adjust max_batch_size to avoid OOM errors
    # Add embeddings to collection
    for i in range(0, len(all_embeddings), max_batch_size):
        batch_embeddings = all_embeddings[i : i + max_batch_size]
        batch_ids = [str(j) for j in range(i, i + len(batch_embeddings))]
        collection.add(embeddings=batch_embeddings.tolist(), ids=batch_ids)

    return collection

def maybe_list(x: Any) -> list[Any]:
    if isinstance(x, list):
        return x
    else:
        return [x]

def hash_key(key: str) -> str:
    # returns a 64-char hex string
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

def shard_id(hashed_key: str, num_shards: int) -> int:
    h = int(hashed_key, 16)
    return h % num_shards

def lookup_web_content(db_dir, key):
    num_shards = max([int(i.split('.mdb')[0].replace('shard_', '')) for i in os.listdir(db_dir) if '.mdb' in i]) + 1
    hashed_key = hash_key(key)
    sid = shard_id(hashed_key, num_shards)
    env = lmdb.open(
        os.path.join(db_dir, f"shard_{sid}.mdb"),
        readonly=True,
        lock=False,
        subdir=False
    )
    with env.begin() as txn:
        raw = txn.get(hashed_key.encode("utf-8"))
    env.close()
    return json.loads(raw) if raw else None

def load_from_hf(hf_path, revision=None):
    try:
        from huggingface_hub import snapshot_download
        dataset_local_path = snapshot_download(
            repo_id=hf_path, 
            repo_type="dataset",
            revision=revision
        )
        return dataset_local_path
    except Exception as e:
        raise