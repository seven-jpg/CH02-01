import os
from typing import Any, Union

import chromadb
import numpy as np
import torch
from PIL import Image
from cragmm_search.utils import add_embeddings_to_collection

IMG_EMB_PATH = "embeddings.npy"

# TODO: remove this function (not needed)
def index_image_kg(image_index_path: Union[str, None] = None) -> chromadb.Collection:
    # Load embeddings from file
    if isinstance(image_index_path, str):
        embs = np.load(os.path.join(image_index_path, IMG_EMB_PATH)).astype("float32")
    else:
        embs = np.load(IMG_EMB_PATH).astype("float32")

    # Create a ChromaDB client and collection
    client = chromadb.Client()

    collection_name = f"image_embeddings"
    if collection_name in client.list_collections():
        print(
            f"Collection {collection_name} already exists. Using existing collection."
        )
        collection = client.get_collection(name=collection_name)
    else:
        collection = client.create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )

        # Add embeddings to the collection
        collection = add_embeddings_to_collection(collection, embs)

    return collection


def extract_features(
    model: torch.nn.Module,
    processor: Any,
    image: Image.Image,
    device: Union[torch.device, None] = None,
) -> np.ndarray:
    if device is None:
        device = model.device

    inputs = processor(images=image, return_tensors="pt")
    # Move inputs to the same device as the model
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        features = model.get_image_features(**inputs)

    # Normalize features
    features = features / features.norm(dim=-1, keepdim=True)
    return features.cpu().numpy()


def image_search(img_emb, collection, top_n: int) -> list[tuple[int, float]]:
    # Ensure img_emb is in the right format
    if img_emb.ndim == 1:
        img_emb = img_emb.reshape(1, -1)

    # Normalize the embedding (ChromaDB doesn't do this automatically)
    norm = np.linalg.norm(img_emb)
    if norm > 0:
        img_emb = img_emb / norm

    # Query the collection
    results = collection.query(query_embeddings=img_emb.tolist(), n_results=top_n)

    # Extract and return indices and distances
    indices = [int(id) for id in results["ids"][0]]
    distances = (
        results["distances"][0] if "distances" in results else [1.0] * len(indices)
    )

    # Convert distances to similarity scores (1 - distance)
    scores = [1.0 - d for d in distances]

    return list(zip(indices, scores))
