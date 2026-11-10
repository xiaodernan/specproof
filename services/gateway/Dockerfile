# SpecProof Edge Gateway — two-stage build.
#
# Stage 1 builds the boot jar from sources (no host toolchain required);
# stage 2 is a JRE-only runtime image.
#
# Build:
#   docker build -t specproof-gateway:local D:\面试项目\specproof-reference\services\gateway
# Rebuild from the observability stack:
#   docker compose -f compose.observability.yml build specproof-edge

FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /gateway
COPY pom.xml .
RUN mvn -B dependency:go-offline
COPY src ./src
RUN mvn -B package -DskipTests

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /gateway/target/gateway-0.1.0.jar /app.jar
EXPOSE 8080 8090
ENTRYPOINT ["java", "-jar", "/app.jar"]
