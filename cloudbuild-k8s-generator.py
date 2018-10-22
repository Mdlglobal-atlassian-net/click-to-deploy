#!/usr/bin/env python
#
# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

CLOUDBUILD_CONFIG = 'cloudbuild.yaml'

HEADER = """timeout: 1200s # 20m
options:
  machineType: 'N1_HIGHCPU_8'
steps:
"""

INITIALIZE_GIT = """
- id: Initialize Git
  name: gcr.io/cloud-builders/git
  entrypoint: bash
  args:
  - -exc
  - |
    # Cloud Build x GitHub integration uses source archives to fetch
    # the source, rather than Git source fetching, and as a consequence
    # does not include the .git/ directory. As a workaround, we clone
    # the repository and reset it to this build's commit sha.
    git clone https://github.com/GoogleCloudPlatform/click-to-deploy.git .tmp
    mv .tmp/.git .git
    rm -rf .tmp
    git reset "$COMMIT_SHA"

    # Download Git submodules
    git submodule init
    git submodule sync --recursive
    git submodule update --recursive --init
"""

PULL_DEV_IMAGE = """
- id: Pull Dev Image
  name: gcr.io/cloud-builders/docker
  waitFor:
  - Initialize Git
  dir: k8s/vendor/marketplace-tools
  entrypoint: bash
  args:
  - -exc
  - |
    TAG="$$(./scripts/derive_tag.sh)"
    docker pull "gcr.io/cloud-marketplace-tools/k8s/dev:$$TAG"
    docker tag "gcr.io/cloud-marketplace-tools/k8s/dev:$$TAG" "gcr.io/cloud-marketplace-tools/k8s/dev:local"
"""

GET_KUBERNETES_CREDENTIALS = """
# TODO(wgrzelak): Replace cluster-name and cluster-location with variables.
- id: Get Kubernetes Credentials
  name: gcr.io/cloud-builders/gcloud
  args:
  - container
  - clusters
  - get-credentials
  - 'limani-integ'
  - --region
  - 'us-central1'
  - --project
  - '$PROJECT_ID'
"""

COPY_KUBECTL_CREDENTIALS = """
- id: Copy kubectl Credentials
  name: gcr.io/google-appengine/debian9
  waitFor:
  - Get Kubernetes Credentials
  entrypoint: bash
  args:
  - -exc
  - |
    mkdir -p /workspace/.kube/
    cp -r $$HOME/.kube/ /workspace/
"""

COPY_GCLOUD_CREDENTIALS = """
- id: Copy gcloud Credentials
  name: gcr.io/google-appengine/debian9
  waitFor:
  - Get Kubernetes Credentials
  entrypoint: bash
  args:
  - -exc
  - |
    mkdir -p /workspace/.config/gcloud/
    cp -r $$HOME/.config/gcloud/ /workspace/.config/
"""

SOLUTION_BUILD_STEP_TEMPLATE = """
- id: Verify <SOLUTION>
  name: gcr.io/cloud-marketplace-tools/k8s/dev:local
  waitFor:
  - Copy kubectl Credentials
  - Copy gcloud Credentials
  - Pull Dev Image
  env:
  - 'KUBE_CONFIG=/workspace/.kube'
  - 'GCLOUD_CONFIG=/workspace/.config/gcloud'
  # Use local Docker network named cloudbuild as described here:
  # https://cloud.google.com/cloud-build/docs/overview#build_configuration_and_build_steps
  - 'EXTRA_DOCKER_PARAMS=--net cloudbuild'
  dir: k8s/<SOLUTION>
  args:
  - -exc
  - make -j4 app/verify
"""


def main():
  skiplist = ['spark-operator']

  cloudbuild_contents = ''.join([
      HEADER, INITIALIZE_GIT, PULL_DEV_IMAGE, GET_KUBERNETES_CREDENTIALS,
      COPY_KUBECTL_CREDENTIALS, COPY_GCLOUD_CREDENTIALS
  ])

  listdir = os.listdir('k8s')
  listdir.remove('vendor')
  listdir.sort()

  for solution in listdir:
    if solution in skiplist:
      print('Skipping solution: ' + solution)
    else:
      print('Adding config for solution: ' + solution)
      # TODO(wgrzelak): Use python string format instead of replace.
      solution_build = SOLUTION_BUILD_STEP_TEMPLATE.replace(
          '<SOLUTION>', solution)
      cloudbuild_contents += solution_build

  with open(CLOUDBUILD_CONFIG, 'w') as cloudbuild_file:
    cloudbuild_file.write(cloudbuild_contents)


if __name__ == '__main__':
  main()
