SHELL := /bin/sh
IMAGE ?= razeencheng/dsh
TAG ?= local
BUILDER ?= dsh-multiarch
PLATFORMS ?= linux/amd64,linux/arm64
DSH_REF ?= 1f81c047fc48fa190a683e469daa699857e9afe8
DSH_TAG ?= dsh-v0.2.1-rc.3
INSTALL_PYTHON ?= true
INSTALL_GO ?= true
INSTALL_DOCKER ?= true
PACKAGING_REVISION ?= 1
BUILD_ARGS = --build-arg DSH_REF=$(DSH_REF) --build-arg DSH_TAG=$(DSH_TAG) \
 --build-arg INSTALL_PYTHON=$(INSTALL_PYTHON) --build-arg INSTALL_GO=$(INSTALL_GO) \
 --build-arg INSTALL_DOCKER=$(INSTALL_DOCKER) --build-arg PACKAGING_REVISION=$(PACKAGING_REVISION)

.PHONY: help build builder build-all push test smoke check run inspect
help:
	@printf '%s\n' \
	 'make build                  Build the native image' \
	 'make build-all              Build/load both Linux architectures' \
	 'make smoke                  Test native image tools, Web and sandbox' \
	 'make test                   Test release planning' \
	 'make check                  Test scripts and Compose syntax' \
	 'make push TAG=...           Explicitly build/push a multi-arch image' \
	 'make run                    Start the configured Compose deployment' \
	 'Optional: INSTALL_PYTHON=false INSTALL_GO=false INSTALL_DOCKER=false' \
	 'Custom upstream: DSH_REF=<commit> DSH_TAG=dsh-v<version>'
build:
	docker build $(BUILD_ARGS) -t $(IMAGE):$(TAG) .
builder:
	@docker buildx inspect $(BUILDER) >/dev/null 2>&1 || docker buildx create --name $(BUILDER)
	@docker buildx inspect --bootstrap $(BUILDER) >/dev/null
build-all: builder
	docker buildx build --builder $(BUILDER) --platform linux/amd64 $(BUILD_ARGS) --tag $(IMAGE):$(TAG)-amd64 --load .
	docker buildx build --builder $(BUILDER) --platform linux/arm64 $(BUILD_ARGS) --tag $(IMAGE):$(TAG)-arm64 --load .
push: builder
	docker buildx build --builder $(BUILDER) --platform $(PLATFORMS) $(BUILD_ARGS) --tag $(IMAGE):$(TAG) --push .
test:
	python3 -m unittest discover -s tests -v
	node --test docker/*.test.mjs
smoke:
	bash scripts/smoke-test.sh $(IMAGE):$(TAG) $(INSTALL_PYTHON) $(INSTALL_GO) $(INSTALL_DOCKER)
check: test
	bash -n scripts/smoke-test.sh
	docker compose config --quiet
	DOCKER_GID=999 docker compose -f docker-compose.yml -f docker-compose.docker.yml config --quiet
run:
	docker compose up -d
inspect:
	docker buildx imagetools inspect $(IMAGE):$(TAG)
