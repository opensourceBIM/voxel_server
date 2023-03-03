FROM ubuntu:20.04

WORKDIR /

ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get -y update && apt-get -y --no-install-recommends --no-install-suggests install wget \
	&& rm -rf /var/lib/apt/lists/*

RUN wget --no-check-certificate -qO /tmp/mc.sh https://github.com/conda-forge/miniforge/releases/latest/download/Mambaforge-Linux-x86_64.sh
RUN chmod +x /tmp/mc.sh
RUN bash /tmp/mc.sh -b -p /conda
RUN /conda/bin/mamba install -y python=3.9 pythonocc-core numpy ifcopenshell
RUN /conda/bin/mamba install -y -c ifcopenshell voxelization_toolkit
ENV PATH="/conda/bin:${PATH}"

RUN python3 -m pip install flask flask-cors Pillow gunicorn
ADD server /voxels/server/
WORKDIR /voxels/server

ENTRYPOINT gunicorn --bind 0.0.0.0:5000 --timeout 3600 wsgi
