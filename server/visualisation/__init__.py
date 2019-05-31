import numpy

from PIL import Image

def create_image(arr, axis, offset, grid=-1, colors=None):

    if colors is None:
        colors = numpy.array([(255,255,255,0),(0,0,0,255)], dtype=numpy.uint16)
        colors = numpy.array([(50),(255)], dtype=numpy.uint16)
    else:
        colors = numpy.array(colors, dtype=numpy.uint16)

    key = [slice(None)] * 3
    key[axis] = offset
    a = colors[numpy.clip(arr[tuple(key)], 0, len(colors) - 1)]
    
    if grid > 0:
        a[::grid,:] *= 5
        a[:,::grid] *= 5
        a[::grid,:] //= 8
        a[:,::grid] //= 8
    
    im = Image.fromarray(numpy.transpose(numpy.uint8(a), (1,0))[::-1,:])
    return im            

    
class image_builder(object):

    def __init__(self, color, grid=-1):
        self.a = None
        self.mask = None
        self.bg = color
        
    def add(self, arr, axis, offset, color):
        colors = numpy.array([self.bg, color[0:3]], dtype=numpy.uint16)

        try:
            alpha = numpy.float64(color[3]) / 255.
        except:
            alpha = None

        
        key = [slice(None)] * 3
        key[axis] = offset
        
        d = arr[tuple(key)]
        # mask = d == 0
        
        a = colors[numpy.clip(d, 0, len(colors) - 1)]
        
        if self.a is None:
            self.a = a
            # self.mask = mask
        else:
            if alpha is None:
                self.a[d > 0, :] = a[d > 0, :]
            else:
                self.a[d > 0, :] = numpy.float64(self.a[d > 0, :]) * (1. - alpha) + numpy.float64(a[d > 0, :]) * alpha
            # self.a[~mask] = a[~mask]
            # self.mask[mask] = False
            
    def grid(self, spacing):
        self.a[::spacing,:] *= 5
        self.a[:,::spacing] *= 5
        self.a[::spacing,:] //= 8
        self.a[:,::spacing] //= 8
            
    def image(self):
        if self.a is None:
            raise ValueError("Call add() first")
        return Image.fromarray(numpy.transpose(numpy.uint8(self.a), (1,0,2))[::-1,:])