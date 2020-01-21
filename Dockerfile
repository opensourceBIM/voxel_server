FROM ubuntu:16.04 as ifcopenshell

WORKDIR /
RUN apt-get -y update && apt-get -y install autoconf bison build-essential git make wget python bzip2 libfreetype6-dev mesa-common-dev libgl1-mesa-dev python-pip libftgl-dev cmake unzip libffi-dev
RUN git clone https://github.com/IfcOpenShell/IfcOpenShell.git && cd IfcOpenShell && git checkout v0.6.0
WORKDIR /IfcOpenShell/nix
RUN CXXFLAGS="-O3 -march=native" BUILD_CFG=Release python build-all.py IfcGeom

# Install boost::filesystem
WORKDIR /IfcOpenShell/build/Linux/x86_64/build/boost_1_59_0
RUN ./b2 --stagedir=/IfcOpenShell/build/Linux/x86_64/install/boost-1.59.0 \
        --with-system --with-program_options --with-regex --with-thread \
        --with-date_time --with-iostreams --with-filesystem \
        \
        link=static \
        \
        cxxflags=-O3 cxxflags=-march=native cxxflags=-fPIC cxxflags=-fdata-sections \
        cxxflags=-ffunction-sections cxxflags=-fvisibility=hidden cxxflags=-fvisibility-inlines-hidden \
        linkflags=-Wl,--gc-sections \
        stage -s NO_BZIP2=1

ADD voxel/*.cpp voxel/*.h voxel/*.txt* /voxels/voxel/
ADD voxel/tests/* /voxels/voxel/tests/
ADD voxel/tests/fixtures/* /voxels/voxel/tests/fixtures/
WORKDIR /voxels/voxel/build
RUN CXXFLAGS="-O3 -march=native" /IfcOpenShell/build/Linux/x86_64/build/cmake-3.4.3/build/bin/cmake .. -DIFCOPENSHELL_ROOT=/IfcOpenShell  -DCMAKE_BUILD_TYPE=Release
RUN make -j

# Get IFC files for tests
RUN wget -O duplex.zip https://portal.nibs.org/files/wl/?id=4DsTgHFQAcOXzFetxbpRCECPbbfUqpgo && \
       unzip -j duplex.zip Duplex_A_20110907_optimized.ifc && \
       mv Duplex_A_20110907_optimized.ifc duplex.ifc
RUN wget -O schependom.ifc "https://github.com/openBIMstandards/DataSetSchependomlaan/raw/master/Design model IFC/IFC Schependomlaan.ifc"

RUN make test
RUN make install

# pip needs to install numpy first
# https://github.com/pypa/pip/issues/6667#issuecomment-507164431
RUN python -m pip install numpy==1.16.5
RUN python -m pip install flask flask-cors Pillow==6.2.2 gunicorn==19.9.0

ADD https://s3.amazonaws.com/ifcopenshell-builds/ifcopenshell-python-27u-v0.6.0-b4ce5be-linux64.zip /tmp/ifcopenshell.zip
RUN unzip /tmp/ifcopenshell.zip -d /usr/lib/python2.7/dist-packages
ADD server /voxels/server/
WORKDIR /voxels/server

ENTRYPOINT gunicorn --bind 0.0.0.0:5000 --timeout 3600 wsgi
