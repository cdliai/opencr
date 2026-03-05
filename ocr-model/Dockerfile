FROM vllm/vllm-openai:latest
ENTRYPOINT ["python", "-m", "vllm.entrypoints.openai.api_server"]
CMD [ \
    "--model", "deepseek-ai/DeepSeek-OCR", \
    "--trust-remote-code", \
    "--logits-processors", "vllm.model_executor.models.deepseek_ocr:NGramPerReqLogitsProcessor", \
    "--no-enable-prefix-caching", \
    "--mm-processor-cache-gb", "0", \
    "--max-model-len", "8192", \
    "--gpu-memory-utilization", "0.85", \
    "--host", "0.0.0.0", \
    "--port", "39671" \
]
