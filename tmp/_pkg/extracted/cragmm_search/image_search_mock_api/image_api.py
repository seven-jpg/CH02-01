import os
from io import BytesIO
from typing import Any, Union

import requests
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor, Pipeline
from cragmm_search.utils import maybe_list

from .image_kg import CragImageKG


# Create a custom pipeline that inherits from transformers.Pipeline
class ImageSearchPipeline(Pipeline):
    def __init__(self, image_hf_dataset_id, **kwargs):
        # Determine the device to use
        device_str = (
            "cuda"
            if torch.cuda.is_available()
            else "mps" if torch.backends.mps.is_available() else "cpu"
        )
        device = torch.device(device_str)
        print(f"Using device: {device}")

        # Create model and processor
        model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14-336")
        model = model.to(device)
        model.eval()
        processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14-336")

        # Initialize with minimal arguments
        super().__init__(
            model=model,
            framework="pt",  # Specify framework to avoid inference
            device=device,  # Pass the torch.device object, not a string
            **kwargs,
        )
        # Don't override the device attribute set by the parent class
        self.crag_image_kg = CragImageKG(model, processor, image_hf_dataset_id)

    def load_image_from_url(self, url: str) -> Image.Image:
        cache_dir = os.path.join(
            os.path.expanduser("~"), ".cragmm_cache", "image_cache"
        )
        os.makedirs(cache_dir, exist_ok=True)
        image_path = os.path.join(cache_dir, os.path.basename(url))

        if os.path.exists(image_path):
            image = Image.open(image_path)
        else:
            response = requests.get(url)
            if response.status_code == 200:
                image = Image.open(BytesIO(response.content))
                image.save(image_path)
            else:
                raise Exception(
                    f"Failed to retrieve image. Status code: {response.status_code}"
                )
        return image

    def _sanitize_parameters(self, **kwargs):
        """
        Handle optional parameters for the pipeline
        """
        preprocess_params = {}
        forward_params = {}
        postprocess_params = {}

        # Extract parameters for different stages
        if "k" in kwargs:
            forward_params["k"] = kwargs["k"]

        return preprocess_params, forward_params, postprocess_params

    def preprocess(self, query_img: Union[str, Image.Image]) -> dict[str, Image.Image]:
        """
        Preprocess the input image URL
        """
        if isinstance(query_img, str):
            return {"img": self.load_image_from_url(query_img)}
        else:
            return {"img": query_img}

    def _forward(self, model_inputs: dict[str, Any], k: int = 5) -> dict[str, Any]:
        """
        Perform the image search
        """
        img = model_inputs["img"]
        results = self.crag_image_kg.image_search(img, k)
        return {"raw_results": results}

    def postprocess(self, model_outputs: dict[str, Any]) -> dict[str, Any]:
        """
        Format the results
        """
        results = model_outputs["raw_results"]
        formatted_results = [
            {
                "index": ind,
                "dist": d,
                "image_url": self.crag_image_kg.get_image_url(ind),
                "entities": [
                    {
                        "entity_name": entity,
                        "entity_attributes": self.crag_image_kg.get_entity(
                            entity_name=entity
                        ),
                    }
                    for entity in maybe_list(self.crag_image_kg.get_entity_name(ind))
                ],
            }
            for ind, d in results
        ]
        return {"results": formatted_results}


# Register the pipeline with Hugging Face
from transformers.pipelines import PIPELINE_REGISTRY

# Define the pipeline configuration
PIPELINE_REGISTRY.register_pipeline(
    "image-search",
    pipeline_class=ImageSearchPipeline,
    pt_model=None,
    default={"pt": (None, None)},  # Provide an instance as the default
)


# Create a factory function to instantiate the pipeline
def pipeline(image_hf_dataset_id: str) -> Pipeline:
    """Create and return an instance of the ImageSearchPipeline directly"""
    # Create the pipeline directly to avoid HF pipeline factory issues
    return ImageSearchPipeline(image_hf_dataset_id)
