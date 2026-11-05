FROM rust:1-slim-bookworm AS build
WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release

FROM debian:bookworm-slim
RUN useradd -r -u 10001 -m -d /app ctf
WORKDIR /app
COPY --from=build /src/target/release/rustwallet /app/rustwallet
COPY flag.txt /app/flag.txt
RUN mkdir -p /app/plugins && chown -R ctf:ctf /app
USER ctf
ENV PORT=7777
ENV FLAG_FILE=/app/flag.txt
EXPOSE 7777
ENTRYPOINT ["/app/rustwallet"]
