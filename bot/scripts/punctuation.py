"""Punctuation and truecasing restoration through a local ONNX model, no torch runtime"""
from __future__ import annotations

import numpy as np
import onnxruntime as ort
import yaml
from huggingface_hub import hf_hub_download
from sentencepiece import SentencePieceProcessor

MODEL_REPO = "1-800-BAD-CODE/xlm-roberta_punctuation_fullstop_truecase"
NULL_LABEL = "<NULL>"
ACRONYM_LABEL = "<ACRONYM>"
OVERLAP = 16


class PunctuationRestorer:
    def __init__(self, spe_path: str, onnx_path: str, config: dict):
        self._sp = SentencePieceProcessor(spe_path)
        self._session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        self._max_len = config["max_length"]
        self._pre_labels = config["pre_labels"]
        self._post_labels = config["post_labels"]

    @classmethod
    def from_pretrained(cls, repo: str = MODEL_REPO) -> "PunctuationRestorer":
        spe_path = hf_hub_download(repo, "sp.model")
        onnx_path = hf_hub_download(repo, "model.onnx")
        config = yaml.safe_load(open(hf_hub_download(repo, "config.yaml")))
        return cls(spe_path, onnx_path, config)

    def restore(self, text: str) -> list[str]:
        return self._decode(*self._predict(text))

    def _predict(self, text: str):
        token_ids = self._sp.EncodeAsIds(text)
        chunk_len = self._max_len - 2
        chunks: list[list[int]] = []
        start = 0
        index = 0
        while start < len(token_ids):
            adjusted = start if index == 0 else start - OVERLAP
            stop = adjusted + chunk_len
            chunks.append(token_ids[adjusted:stop])
            start = stop
            index += 1

        ids: list[int] = []
        pre: list[int] = []
        post: list[int] = []
        cap: list[list[bool]] = []
        sbd: list[bool] = []
        for i, chunk in enumerate(chunks):
            framed = np.array([[self._sp.bos_id(), *chunk, self._sp.eos_id()]], dtype=np.int64)
            pre_out, post_out, cap_out, sbd_out = self._session.run(None, {"input_ids": framed})
            inner = slice(1, framed.shape[1] - 1)
            lo = OVERLAP // 2 if i > 0 else 0
            hi = len(chunk) - (OVERLAP // 2 if i < len(chunks) - 1 else 0)
            ids.extend(chunk[lo:hi])
            pre.extend(pre_out[0, inner][lo:hi].tolist())
            post.extend(post_out[0, inner][lo:hi].tolist())
            cap.extend(cap_out[0, inner][lo:hi].tolist())
            sbd.extend(sbd_out[0, inner][lo:hi].tolist())
        return ids, pre, post, cap, sbd

    def _decode(self, ids, pre_idx, post_idx, cap, sbd) -> list[str]:
        pre = [self._resolve(self._pre_labels, p) for p in pre_idx]
        post = [self._resolve(self._post_labels, p) for p in post_idx]
        pieces = [self._sp.IdToPiece(x) for x in ids]
        sentences: list[str] = []
        chars: list[str] = []
        for i, piece in enumerate(pieces):
            if piece.startswith("▁") and chars:
                chars.append(" ")
            char_start = 1 if piece.startswith("▁") else 0
            for char_idx, char in enumerate(piece[char_start:], start=char_start):
                if char_idx == char_start and pre[i] is not None:
                    chars.append(pre[i])
                if char_idx < len(cap[i]) and cap[i][char_idx]:
                    char = char.upper()
                chars.append(char)
                if post[i] == ACRONYM_LABEL:
                    chars.append(".")
                elif char_idx == len(piece) - 1 and post[i] is not None:
                    chars.append(post[i])
                if char_idx == len(piece) - 1 and sbd[i]:
                    sentences.append("".join(chars))
                    chars = []
        if chars:
            sentences.append("".join(chars))
        return sentences

    @staticmethod
    def _resolve(labels, index):
        label = labels[index]
        return None if label == NULL_LABEL else label
