FROM rust:1.89-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        pkg-config \
        libcapstone-dev \
        libunicorn-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY Cargo.toml Cargo.lock ./
COPY src ./src
COPY profiles ./profiles
COPY vendor ./vendor

RUN cargo build --release \
    && cargo build --release --manifest-path vendor/stm32-emulator/stm32-emulator-main/Cargo.toml

ENV TERM=xterm-256color

ENTRYPOINT ["/app/target/release/stm32_jeopardy_lab"]
CMD ["--challenge", "sram"]
