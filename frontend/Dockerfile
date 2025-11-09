# ====== STAGE 1: build de React ======
FROM node:20-alpine AS build

WORKDIR /app

# Copiamos package.json y lock para aprovechar la cache
COPY package*.json ./

RUN npm install

# Copiamos el resto del código
COPY . .

# Construimos la app para producción
RUN npm run build

# ====== STAGE 2: Nginx sirviendo estáticos + proxy a backend ======
FROM nginx:alpine

# Eliminamos la config por defecto
RUN rm /etc/nginx/conf.d/default.conf

# Copiamos nuestra config de Nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copiamos el build de React
COPY --from=build /app/dist /usr/share/nginx/html
# (si usas CRA en vez de Vite, cambia /app/dist por /app/build)

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
