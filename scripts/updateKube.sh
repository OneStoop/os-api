#!/bin/sh
sed -i "s/{{VERSION}}/${TRAVIS_BUILD_NUMBER}/g" kube/deployment.yml
sed -i "s/{{BASE_URL}}/${BASE_URL}/g" kube/deployment.yml
sed -i "s/{{ARANGODB_SETTINGS}}/${ARANGODB_SETTINGS}/g" kube/deployment.yml
sed -i "s/{{FIREBASE_CONFIG}}/${FIREBASE_CONFIG}/g" kube/deployment.yml
sed -i "s/{{SPACES_KEY}}/${SPACES_KEY}/g" kube/deployment.yml
sed -i "s/{{SPACES_SECRET}}/${SPACES_SECRET}/g" kube/deployment.yml
