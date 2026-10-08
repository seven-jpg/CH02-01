import json
from huggingface_hub import snapshot_download
import chromadb
from typing import Any, Union
import torch
from PIL import Image
import os

from .image_search import (
    extract_features,
    image_search,
)

class CragImageKG(object):
    def __init__(
        self, 
        emb_model: torch.nn.Module, 
        processor: Any, 
        hf_dataset_id: str,
        image_hf_dataset_tag: str = None
    ):
        print(f"Loading image index from huggingface {hf_dataset_id}")
        dataset_local_path = snapshot_download(
            repo_id=hf_dataset_id, 
            repo_type="dataset",
            revision=image_hf_dataset_tag
        )

        n_threads = os.cpu_count() or 1
        client = chromadb.PersistentClient(path=dataset_local_path)
        self.vector_db = client.get_collection(name="image_embeddings")
        # reset number of threads; index will be re-built when querying
        self.vector_db .modify(metadata={"hnsw:num_threads": n_threads})

        self.id2_data = self.vector_db.get(include=["metadatas"])['metadatas']
        self.kg = {}
        for data in self.id2_data:
            info = json.loads(data['info'])
            for entity in info:
                self.kg[entity] = info[entity]
        self.emb_model = emb_model
        self.processor = processor

    def image_search(
        self, query_img: Image.Image, k: int = 5
    ) -> list[tuple[int, float]]:
        # Make sure the query image is processed on the same device as the model
        device = self.emb_model.device
        query_img_emb = extract_features(
            self.emb_model, self.processor, query_img, device
        )
        top_k = image_search(query_img_emb, self.vector_db, top_n=k)
        return top_k

    def get_image_url(self, image_id: int) -> str:
        return self.id2_data[image_id]["image_url"]

    def get_entity_name(self, image_id: int) -> Union[str, list[str]]:
        return json.loads(self.id2_data[image_id]["entities"])

    def get_entity(self, entity_name: str) -> dict[str, Any]:
        return self.kg[entity_name]
