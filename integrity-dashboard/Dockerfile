FROM node:22-alpine

# Baked-in content fingerprint of this service's tracked source — see
# scripts/service_content_hash.py and PRODUCTION_GAPS.md §22.
ARG SOURCE_HASH=unknown
LABEL source.hash=$SOURCE_HASH

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm install

COPY . .

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
