# example usage:
# python image_search_mock_api/generate_index.py --index-data-dir data/image_index_data --output-dir image_search_mock_api/mock_kg_test
import os
import json
import numpy as np
import torch
import requests
from PIL import Image
from io import BytesIO
from transformers import CLIPModel, CLIPProcessor
from pathlib import Path
import argparse

# Default configuration
EMBEDDING_DIM = 512  # CLIP's embedding dimension
DEFAULT_OUTPUT_DIR = "image_search_mock_api/mock_kg"
DEFAULT_INDEX_DATA_DIR = "data/image_index_data"


def ensure_directory_exists(directory):
    """Create directory if it doesn't exist."""
    Path(directory).mkdir(parents=True, exist_ok=True)

def load_image_from_url(url):
    """Load an image from a URL."""
    response = requests.get(url)
    if response.status_code == 200:
        return Image.open(BytesIO(response.content))
    else:
        raise Exception(f"Failed to retrieve image. Status code: {response.status_code}")

def extract_features(model, processor, image, device):
    """Extract features from an image using CLIP."""
    inputs = processor(images=image, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        features = model.get_image_features(**inputs)

    # Normalize features
    features = features / features.norm(dim=-1, keepdim=True)
    return features.cpu().numpy()

def generate_index(index_data_dir, output_dir):
    """Generate mock data for the image search API."""
    ensure_directory_exists(output_dir)

    # Determine device
    device_str = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    device = torch.device(device_str)
    print(f"Using device: {device}")

    # Load CLIP model and processor
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch16")
    model = model.to(device)
    model.eval()
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch16")

    # Generate embeddings
    embeddings = []
    image_id_to_data = {}
    kg = {}

    with open(os.path.join(index_data_dir, "image_data.jsonl"), "r") as f:
        for i, line in enumerate(f):
            data = json.loads(line)
            print(f"Processing sample image {i+1}")
            image = load_image_from_url(data["image_url"])
            embedding = extract_features(model, processor, image, device)
            embeddings.append(embedding)
            # Assign URL and entity
            image_id_to_data[str(i)] = {"image_url": data["image_url"], "entities": data["entities"]}

    np.save(os.path.join(output_dir, "embeddings.npy"), embeddings)

    with open(os.path.join(output_dir, "image_id_to_data.json"), "w") as f:
        json.dump(image_id_to_data, f, indent=2)

    # Check if entity_data.json exists in the index_data_dir and copy it to the output dir
    entity_data_path = os.path.join(index_data_dir, "entity_data.json")
    if os.path.exists(entity_data_path):
        print(f"Found entity_data.json, copying to {output_dir} as kg.json")
        # Read the entity data
        with open(entity_data_path, "r") as f:
            entity_data = json.load(f)

        # Write it to the output directory as kg.json
        with open(os.path.join(output_dir, "kg.json"), "w") as f:
            json.dump(entity_data, f, indent=2)
    else:
        print("No entity_data.json found in the index data directory")

    print(f"Generated mock data in {output_dir}:")
    print(f"- embeddings.npy: {len(embeddings)} embeddings")
    print(f"- image_id_to_data.json: {len(image_id_to_data)} entries")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate image search index from image data")
    parser.add_argument(
        "--index-data-dir",
        default=DEFAULT_INDEX_DATA_DIR,
        help=f"Path to input image data directory (default: {DEFAULT_INDEX_DATA_DIR})"
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Path to output mock knowledge graph directory (default: {DEFAULT_OUTPUT_DIR})"
    )
    args = parser.parse_args()

    print(f"Generating index from {args.index_data_dir} to {args.output_dir}...")
    generate_index(args.index_data_dir, args.output_dir)
