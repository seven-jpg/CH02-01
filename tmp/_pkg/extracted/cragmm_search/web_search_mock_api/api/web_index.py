from .web_search import extract_features, index_web_data, web_search


class CragMockWeb(object):
    def __init__(
        self, emb_model, tokenizer, text_index_path, web_hf_dataset_tag=None
    ):
        self.vector_db = index_web_data(hf_path=text_index_path, revision=web_hf_dataset_tag)
        self.emb_model = emb_model
        self.tokenizer = tokenizer
        self.index_to_metadata = dict(zip(self.vector_db.get()['ids'], self.vector_db.get(include=["metadatas"])['metadatas']))

    # TODO: this is not used, to be deprecated
    def search(self, query, k=5):
        # Make sure the query is processed on the same device as the model
        device = self.emb_model.device
        query_emb = extract_features(self.emb_model, self.tokenizer, query, device)

        # Retrieve more chunks, e.g., 100
        top_chunks = web_search(query_emb, self.vector_db, top_n=100)

        # Deduplicate by page_url
        unique_results = {}
        for idx, score in top_chunks:
            page_url = self.get_page_url(idx)
            if page_url not in unique_results:
                unique_results[page_url] = (idx, score)

        # Sort by score and return top k
        sorted_results = sorted(unique_results.values(), key=lambda x: x[1], reverse=True)
        return sorted_results[:k]

    def get_page_name(self, idx):
        # Return the page name for a given index
        return self.index_to_metadata[str(idx)]["page_name"]

    def get_page_snippet(self, idx):
        # Return the page name for a given index
        return self.index_to_metadata[str(idx)]["page_snippet"]

    def get_page_url(self, idx):
        # Return the page URL for a given index
        return self.index_to_metadata[str(idx)]["page_url"]
