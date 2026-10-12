#!/usr/bin/env bash
# Render / Railway build step.
#
# `migrate` must run on every deploy: uploaded product images are stored in the
# database (store.MediaFile), so a deploy that skips migrations would leave the
# admin unable to save images.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
