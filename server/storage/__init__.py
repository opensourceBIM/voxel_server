from __future__ import print_function

import os
import numpy

class voxel_storage:
    @staticmethod
    def load(fn, lazy=False):
        meta = fn + ".meta" 
        fm = open(meta)
        header = fm.readline().strip()
        if header == "CONT":
            shape_bit = tuple(map(lambda l: int(l.strip()), fm)) 
            return continous_storage(fn, shape_bit)
        elif header == "CHUNK":
            chunksize = int(fm.readline().strip())
            chunks = tuple(map(lambda l: int(l.strip()), fm))
            return chunked_storage(fn, chunksize, chunks)
        elif header == "CHUNK2":
            # updated serialization with origin included
            voxelsize = float(fm.readline().strip())
            chunksize = int(fm.readline().strip())
            strs = fm.readline().strip().split(';')
            origin = tuple(map(float, strs))
            strs = fm.readline().strip().split(';')
            chunks = tuple(map(int, strs))
            return [chunked_storage, chunked_storage_meta][lazy](fn, chunksize, chunks, origin, voxelsize)
            
            
EXPLICIT, IMPLICIT = 1, 2

class chunked_storage_meta(voxel_storage):
    
    def __init__(self, filename, chunksize, numchunks, origin, voxelsize):
        self.filename, self.chunksize, self.numchunks, self.origin, self.voxelsize = \
            filename, chunksize, numchunks, origin, voxelsize
        self.offset = (0,0,0)


class chunked_storage(voxel_storage):
    
    def __init__(self, fn, chunksize, chunks, origin=None, voxelsize=None):
        # populate by harmonize
        self.offset = (0,0,0)
        self.origin = origin
        self.voxelsize = voxelsize
        self.chunksize = chunksize
        self.chunkdatasize = int(chunksize * chunksize * chunksize // 8)
        
        if os.path.getsize(fn + ".contents") == 0:
            self.data = []
        else:
            self.data = numpy.memmap(fn + ".contents", dtype='uint8', mode='r')
            
        self.primitives = list(map(str.strip, open(fn + ".primitives")))
        
        nx, ny, nz = self.numchunks = self.ownnumchunks = chunks
        s = 0
        self.avail = avail = numpy.zeros((nx, ny, nz, 2), dtype='uint64')
        
        loc = 0 # self.chunkdatasize
        prim = 0
        header = numpy.fromfile(fn + ".index", dtype='uint8')
        
        for i in range(nx):
            for j in range(ny):
                for k in range(nz):
                    a = header[s]
                    s += 1
                    if a == 1:
                        avail[i,j,k] = (1, loc)
                        loc += self.chunkdatasize
                    elif a == 2:
                        avail[i,j,k] = (2, prim)
                        prim += 1
                        
        # print("Chunks: %d x %d x %d = %d, size = %d" % (nx, ny, nz, nx*ny*nz, chunksize)) 
        # print ("Primitive chunks", numpy.count_nonzero(header==2), "/", nx*ny*nz)
        # print ("Non-empty chunks", numpy.count_nonzero(header==1), "/", nx*ny*nz)
        
    def __getattr__(self, k):
        if k == "shape":
            return tuple(c * self.chunksize for c in self.numchunks)
        elif k == "ownshape":
            return tuple(c * self.chunksize for c in self.ownnumchunks)

        
    def __getitem__(self, slices):
    
        # needs exactly one integer slice argument        
        slice_types = list(map(type, slices))
        assert slice_types.count(int) == 1
        assert slice_types.count(slice) == 2
        
        dim = slice_types.index(int)
                
        result_shape = list(self.shape)
        result_shape[dim:dim+1] = []
        
        chunks = list(self.ownnumchunks)
        chunks[dim:dim+1] = []
        
        offset = list(self.offset)
        offset[dim:dim+1] = []
        di, dj = offset
        print("offset", offset)
        
        fixed = slices[dim]
        cs = self.chunksize
        fixed_chunk = fixed // cs
        fixed_index_in_chunk = fixed % cs
        
        img = numpy.full(result_shape, 0, dtype='uint8') # 2
        
        print(slices)
        
        for i in range(chunks[0]):
            for j in range(chunks[1]):
            
                img_subset = img[(i-di)*cs:(i-di+1)*cs,\
                                 (j-dj)*cs:(j-dj+1)*cs]
                                 
                ijk = [i, j]
                ijk.insert(dim, fixed_chunk)
                # print(i,j, *ijk)
            
                chunk_type, chunk_offset = self.avail[tuple(ijk)]
                chunk_offset = int(chunk_offset)
                
                if chunk_type == EXPLICIT:
                    bits = self.data[chunk_offset:chunk_offset + self.chunkdatasize].reshape((cs, cs, cs // 8), order='F')
                    if dim == 2:
                        zc = fixed_index_in_chunk
                        byte_slice = (bits[:,:,zc//8] & (1 << (zc % 8))) != 0
                    else:
                        bytes = numpy.zeros((cs, cs, cs), dtype=bits.dtype)
                        
                        for bit_idx in range(8): 
                            trim = tuple(slice(0,x) for x in bytes[:,:,bit_idx::8].shape) 
                            q = (bits & (1 << bit_idx))[trim] != 0 
                            bytes[:,:,bit_idx::8] = q
                            
                        key = [slice(None)] * 3
                        key[dim] = fixed_index_in_chunk
                        byte_slice = bytes[tuple(key)]
                    img_subset[:] = byte_slice
                        
                elif chunk_type == IMPLICIT:
                    img_subset[:] = 0 # 3
                    for p in self.primitives[chunk_offset].split(','):
                    
                        if p.startswith("CONST"):
                            img_subset[:] = 1
                            
                        else:
                            a, o = p.split('=')
                            ai = "XYZ".index(a)
                            oi = int(o)
                            if ai == dim:
                                if fixed_index_in_chunk == oi:
                                    img_subset[:,:] = 1
                            else:
                                key = [slice(None)] * 3
                                key[ai] = oi
                                key[dim:dim+1] = []
                                img_subset[tuple(key)] = 1
        return img
        
class continous_storage(voxel_storage):
    
    def __init__(self, fn, shape_bit):
        slice_bit = tuple(slice(0,x) for x in shape_bit) 
        dimz = shape_bit[2] 
        shape = shape_bit[0:2] + ((dimz // 8 + (dimz % 8 != 0)),) 
        # fpr = numpy.memmap(fn, dtype='uint8', mode='r', shape=(3,4)) 
        bits = numpy.fromfile(fn, dtype='uint8').reshape(shape, order='F') 
        bytes = numpy.zeros(shape_bit, dtype=bits.dtype) 
        for i in range(8): 
            trim = tuple(slice(0,x) for x in bytes[:,:,i::8].shape) 
            q = (bits & (1 << i))[trim] != 0 
            bytes[:,:,i::8] = q 
        # print("shape", shape, "/", bytes.shape) 
        nz = numpy.count_nonzero 
        # print("nonzero", nz(bits), "/", nz(bytes)) 
        # arr = numpy.uint8(bits != 0) 
        self.arr = bytes 
        self.shape = arr.shape
        
    def __getitem__(self, slice):
        return self.arr[slice]
        
def attr_of_elems(a):
    return lambda elems: [getattr(x, a) for x in elems]

def harmonize(vs):
    vs = list(vs)
    origins = numpy.array(attr_of_elems('origin')(vs))
    origins /= vs[0].chunksize * vs[0].voxelsize
    origins = numpy.int64(numpy.round(origins))
    chunkss = numpy.array(attr_of_elems('numchunks')(vs))
    mins = numpy.amin(origins, axis=0)
    maxs = numpy.amax(origins + chunkss, axis=0)
    print(mins, maxs)
    # Todo immutability
    for v, o in zip(vs, origins):
        v.offset = mins - o
        v.numchunks = maxs - mins
    return vs
    