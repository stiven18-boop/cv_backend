#!/bin/bash
set -e
apt-get update -qq
apt-get install -y -qq tesseract-ocr tesseract-ocr-spa poppler-utils
pip install --upgrade pip
pip install -r requirements.txt