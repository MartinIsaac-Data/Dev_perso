# Development server rather than a static build behind nginx.
#
# This application is served to one person on their own machine. A production
# image would mean a multi-stage build, an nginx config and a rebuild on every
# edit, to serve files to localhost. The dev server gives hot reload instead,
# which is what actually matters here. If this is ever served over a network,
# swap this for a build stage and a static file server.
FROM node:22-slim

WORKDIR /app

# Dependencies first, so editing source does not invalidate the install layer.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# --host binds beyond the loopback interface, without which the port
# published by Compose reaches nothing.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
