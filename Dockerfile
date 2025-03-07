FROM node:14

WORKDIR /app

# Copy package files first
COPY src/package*.json ./
RUN npm install

# Copy source code
COPY src/ ./

EXPOSE 3000

CMD ["node", "app.js"]