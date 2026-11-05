FROM node:20-slim

RUN apt-get update && apt-get install -y \
    chromium \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /bot
COPY package.json .
RUN npm install
COPY bot.js .

CMD ["node", "bot.js"]