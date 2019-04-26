FROM ubuntu:16.04 as ifcopenshell

WORKDIR /
RUN apt-get -y update && apt-get -y install autoconf bison build-essential git make wget python bzip2 libfreetype6-dev mesa-common-dev libgl1-mesa-dev python-pip libftgl-dev cmake unzip
RUN git clone https://github.com/IfcOpenShell/IfcOpenShell.git && cd IfcOpenShell/nix
WORKDIR /IfcOpenShell/nix
RUN CXXFLAGS="-O3 -march=native" BUILD_CFG=Release python build-all.py

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
RUN CXXFLAGS="-O3 -march=native" /IfcOpenShell/build/Linux/x86_64/build/cmake-3.4.1/build/bin/cmake .. -DIFCOPENSHELL_ROOT=/IfcOpenShell  -DCMAKE_BUILD_TYPE=Release
RUN make -j

# Get IFC files for tests
RUN wget -O duplex.zip https://portal.nibs.org/files/wl/?id=4DsTgHFQAcOXzFetxbpRCECPbbfUqpgo && \
       unzip -j duplex.zip Duplex_A_20110907_optimized.ifc && \
       mv Duplex_A_20110907_optimized.ifc duplex.ifc
RUN wget -O schependom.ifc "https://github.com/openBIMstandards/DataSetSchependomlaan/raw/master/Design model IFC/IFC Schependomlaan.ifc"

RUN make test
RUN make install

RUN python -m pip install flask flask-cors numpy Pillow gunicorn

ADD server /voxels/server/
WORKDIR /voxels/server

ENTRYPOINT gunicorn --bind 0.0.0.0:5000 wsgi
