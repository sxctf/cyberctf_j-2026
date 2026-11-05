FROM node:18-alpine

RUN apk add --no-cache \
    chromium \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont

WORKDIR /app
COPY package*.json ./
ENV PUPPETEER_SKIP_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium-browser
RUN npm install --omit=dev

COPY . .

EXPOSE 8080
CMD ["node", "bot.js"]
