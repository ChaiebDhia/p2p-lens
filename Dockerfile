FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir build && python -m build --wheel

FROM python:3.12-slim
RUN useradd --create-home app
COPY --from=build /src/dist/*.whl /tmp/
RUN pip install --no-cache-dir "$(ls /tmp/*.whl)[plots]" && rm /tmp/*.whl
USER app
WORKDIR /work
ENTRYPOINT ["p2p-lens"]
CMD ["--help"]
