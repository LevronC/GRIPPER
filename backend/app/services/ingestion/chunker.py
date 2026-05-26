from typing import List, Dict, Any
from transformers import AutoTokenizer

_tokenizer = None

def get_tokenizer():
    global _tokenizer
    if _tokenizer is None:
        try:
            # Attempt to load the BGE tokenizer from HuggingFace
            _tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-small-en-v1.5")
        except Exception as e:
            # Fallback simple whitespace-based pseudo-tokenizer if offline / error
            class FallbackTokenizer:
                def encode(self, text: str) -> List[str]:
                    return text.split()
                def decode(self, tokens: List[str], skip_special_tokens: bool = True) -> str:
                    return " ".join(tokens)
            _tokenizer = FallbackTokenizer()
    return _tokenizer

def chunk_document_pages(
    pages_data: List[Dict[str, Any]], 
    chunk_size: int = 700, 
    overlap: int = 120
) -> List[Dict[str, Any]]:
    """
    Splits page texts into chunks of a specific token length with overlap.
    Each page is chunked individually to preserve precise page number citations.
    """
    tokenizer = get_tokenizer()
    chunks = []
    
    for page in pages_data:
        page_num = page["page_num"]
        text = page["text"]
        
        if not text.strip():
            continue
            
        tokens = tokenizer.encode(text)
        total_tokens = len(tokens)
        
        # If the page fits within the chunk size, add it as a single chunk
        if total_tokens <= chunk_size:
            chunks.append({
                "page_num": page_num,
                "content": text.strip(),
                "token_count": total_tokens
            })
            continue
            
        # Otherwise, slice with overlap
        start = 0
        while start < total_tokens:
            end = min(start + chunk_size, total_tokens)
            chunk_tokens = tokens[start:end]
            chunk_text = tokenizer.decode(chunk_tokens, skip_special_tokens=True)
            
            if chunk_text.strip():
                chunks.append({
                    "page_num": page_num,
                    "content": chunk_text.strip(),
                    "token_count": len(chunk_tokens)
                })
            
            # Step forward
            start += (chunk_size - overlap)
            
            # Avoid trailing tiny chunks
            if total_tokens - start < overlap:
                break
                
    return chunks
