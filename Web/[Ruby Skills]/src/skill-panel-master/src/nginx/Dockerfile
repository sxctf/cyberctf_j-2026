# FROM registry.ctflab.local/public_images/openresty/openresty:alpine
FROM openresty/openresty:alpine

RUN mkdir -p /var/log/nginx

COPY nginx.conf /usr/local/openresty/nginx/conf/nginx.conf

EXPOSE 80

CMD ["/usr/local/openresty/bin/openresty", "-g", "daemon off;"]
