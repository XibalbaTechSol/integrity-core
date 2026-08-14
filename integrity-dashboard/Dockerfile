FROM node:22-alpine

ARG SOURCE_HASH=unknown
LABEL source.hash=$SOURCE_HASH

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install

COPY . .

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
