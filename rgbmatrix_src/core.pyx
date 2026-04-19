# cython: language_level=3str
# distutils: language = c++

from libcpp cimport bool
from libc.stdint cimport uint8_t, uint32_t, uintptr_t
import cython

cdef class Canvas:
    cdef cppinc.Canvas* _getCanvas(self) except *:
        raise NotImplementedError("Not implemented")

    def SetImage(self, image, int offset_x = 0, int offset_y = 0, unsafe=True):
        cdef int img_width, img_height, x, y, idx
        cdef unsigned char r, g, b
        cdef cppinc.Canvas* canvas
        cdef const unsigned char* data

        # Try the fast unsafe path first (direct PIL pointer access)
        if unsafe:
            try:
                self.SetPixelsPillow(offset_x, offset_y, image.size[0], image.size[1], image)
                return
            except (AttributeError, KeyError, TypeError, OverflowError):
                # unsafe_ptrs not available in this Pillow version, or pointer
                # value overflows uintptr_t on 32-bit ARM (negative int); fall through
                pass

        # Medium-speed path: use tobytes() with nogil loop
        try:
            if image.mode != "RGB":
                image = image.convert("RGB")
            raw_bytes = <bytes>image.tobytes()
            img_width = image.size[0]
            img_height = image.size[1]
            canvas = self._getCanvas()
            data = <const unsigned char*>raw_bytes

            with nogil:
                for y in range(img_height):
                    for x in range(img_width):
                        idx = (y * img_width + x) * 3
                        r = data[idx]
                        g = data[idx + 1]
                        b = data[idx + 2]
                        canvas.SetPixel(offset_x + x, offset_y + y, r, g, b)
            return
        except Exception:
            pass

        # Slowest fallback: pure Python per-pixel
        if image.mode != "RGB":
            image = image.convert("RGB")
        img_width, img_height = image.size
        pixels = image.load()
        for x in range(max(0, -offset_x), min(img_width, self._getCanvas().width() - offset_x)):
            for y in range(max(0, -offset_y), min(img_height, self._getCanvas().height() - offset_y)):
                (r, g, b) = pixels[x, y]
                self._getCanvas().SetPixel(offset_x + x, offset_y + y, r, g, b)

    @cython.boundscheck(False)
    @cython.wraparound(False)
    def SetPixelsPillow(self, int xstart, int ystart, int width, int height, image):
        cdef cppinc.FrameCanvas* my_canvas = <cppinc.FrameCanvas*>self._getCanvas()
        cdef int frame_width = my_canvas.width()
        cdef int frame_height = my_canvas.height()
        cdef int row, col
        cdef int col_start, col_end, row_start, row_end
        cdef uint8_t r, g, b
        cdef uint32_t **image_ptr
        cdef uint32_t pixel
        image.load()
        ptr_tmp = dict(image.im.unsafe_ptrs)['image32']
        image_ptr = (<uint32_t **>(<uintptr_t>ptr_tmp))

        col_start = max(0, -xstart)
        col_end = min(width, frame_width - xstart)
        row_start = max(0, -ystart)
        row_end = min(height, frame_height - ystart)

        with nogil:
            for col in range(col_start, col_end):
                for row in range(row_start, row_end):
                    pixel = image_ptr[row][col]
                    r = (pixel ) & 0xFF
                    g = (pixel >> 8) & 0xFF
                    b = (pixel >> 16) & 0xFF
                    my_canvas.SetPixel(xstart+col, ystart+row, r, g, b)

cdef class FrameCanvas(Canvas):
    def __dealloc__(self):
        if <void*>self.__canvas != NULL:
            self.__canvas = NULL

    cdef cppinc.Canvas* _getCanvas(self) except *:
        if <void*>self.__canvas != NULL:
            return self.__canvas
        raise RuntimeError("Canvas was destroyed or not initialized, you cannot use this object anymore")

    def Fill(self, uint8_t red, uint8_t green, uint8_t blue):
        (<cppinc.FrameCanvas*>self._getCanvas()).Fill(red, green, blue)

    def Clear(self):
        (<cppinc.FrameCanvas*>self._getCanvas()).Clear()

    def SetPixel(self, int x, int y, uint8_t red, uint8_t green, uint8_t blue):
        (<cppinc.FrameCanvas*>self._getCanvas()).SetPixel(x, y, red, green, blue)

    @property
    def width(self):
        return (<cppinc.FrameCanvas*>self._getCanvas()).width()

    @property
    def height(self):
        return (<cppinc.FrameCanvas*>self._getCanvas()).height()

    @property
    def pwmBits(self):
        return (<cppinc.FrameCanvas*>self._getCanvas()).pwmbits()

    @pwmBits.setter
    def pwmBits(self, pwmBits):
        (<cppinc.FrameCanvas*>self._getCanvas()).SetPWMBits(pwmBits)

    @property
    def brightness(self):
        return (<cppinc.FrameCanvas*>self._getCanvas()).brightness()

    @brightness.setter
    def brightness(self, val):
        (<cppinc.FrameCanvas*>self._getCanvas()).SetBrightness(val)


cdef class RGBMatrixOptions:
    def __cinit__(self):
        self.__options = cppinc.Options()
        self.__runtime_options = cppinc.RuntimeOptions()

    # RGBMatrix::Options properties
    @property
    def hardware_mapping(self):
        return self.__options.hardware_mapping

    @hardware_mapping.setter
    def hardware_mapping(self, value):
        self.__py_encoded_hardware_mapping = value.encode('utf-8')
        self.__options.hardware_mapping = self.__py_encoded_hardware_mapping

    @property
    def rows(self):
        return self.__options.rows

    @rows.setter
    def rows(self, int value):
        self.__options.rows = value

    @property
    def cols(self):
        return self.__options.cols

    @cols.setter
    def cols(self, int value):
        self.__options.cols = value

    @property
    def chain_length(self):
        return self.__options.chain_length

    @chain_length.setter
    def chain_length(self, int value):
        self.__options.chain_length = value

    @property
    def parallel(self):
        return self.__options.parallel

    @parallel.setter
    def parallel(self, int value):
        self.__options.parallel = value

    @property
    def pwm_bits(self):
        return self.__options.pwm_bits

    @pwm_bits.setter
    def pwm_bits(self, int value):
        self.__options.pwm_bits = value

    @property
    def pwm_lsb_nanoseconds(self):
        return self.__options.pwm_lsb_nanoseconds

    @pwm_lsb_nanoseconds.setter
    def pwm_lsb_nanoseconds(self, int value):
        self.__options.pwm_lsb_nanoseconds = value

    @property
    def brightness(self):
        return self.__options.brightness

    @brightness.setter
    def brightness(self, int value):
        self.__options.brightness = value

    @property
    def scan_mode(self):
        return self.__options.scan_mode

    @scan_mode.setter
    def scan_mode(self, int value):
        self.__options.scan_mode = value

    @property
    def multiplexing(self):
        return self.__options.multiplexing

    @multiplexing.setter
    def multiplexing(self, int value):
        self.__options.multiplexing = value

    @property
    def row_address_type(self):
        return self.__options.row_address_type

    @row_address_type.setter
    def row_address_type(self, int value):
        self.__options.row_address_type = value

    @property
    def disable_hardware_pulsing(self):
        return self.__options.disable_hardware_pulsing

    @disable_hardware_pulsing.setter
    def disable_hardware_pulsing(self, value):
        self.__options.disable_hardware_pulsing = value

    @property
    def show_refresh_rate(self):
        return self.__options.show_refresh_rate

    @show_refresh_rate.setter
    def show_refresh_rate(self, value):
        self.__options.show_refresh_rate = value

    @property
    def inverse_colors(self):
        return self.__options.inverse_colors

    @inverse_colors.setter
    def inverse_colors(self, value):
        self.__options.inverse_colors = value

    @property
    def led_rgb_sequence(self):
        return self.__options.led_rgb_sequence

    @led_rgb_sequence.setter
    def led_rgb_sequence(self, value):
        self.__py_encoded_led_rgb_sequence = value.encode('utf-8')
        self.__options.led_rgb_sequence = self.__py_encoded_led_rgb_sequence

    @property
    def pixel_mapper_config(self):
        return self.__options.pixel_mapper_config

    @pixel_mapper_config.setter
    def pixel_mapper_config(self, value):
        self.__py_encoded_pixel_mapper_config = value.encode('utf-8')
        self.__options.pixel_mapper_config = self.__py_encoded_pixel_mapper_config

    @property
    def panel_type(self):
        return self.__options.panel_type

    @panel_type.setter
    def panel_type(self, value):
        self.__py_encoded_panel_type = value.encode('utf-8')
        self.__options.panel_type = self.__py_encoded_panel_type

    @property
    def pwm_dither_bits(self):
        return self.__options.pwm_dither_bits

    @pwm_dither_bits.setter
    def pwm_dither_bits(self, int value):
        self.__options.pwm_dither_bits = value

    @property
    def limit_refresh_rate_hz(self):
        return self.__options.limit_refresh_rate_hz

    @limit_refresh_rate_hz.setter
    def limit_refresh_rate_hz(self, int value):
        self.__options.limit_refresh_rate_hz = value


    # RuntimeOptions properties

    @property
    def gpio_slowdown(self):
        return self.__runtime_options.gpio_slowdown

    @gpio_slowdown.setter
    def gpio_slowdown(self, int value):
        self.__runtime_options.gpio_slowdown = value

    @property
    def daemon(self):
        return self.__runtime_options.daemon

    @daemon.setter
    def daemon(self, bool value):
        self.__runtime_options.daemon = value

    @property
    def drop_privileges(self):
        return self.__runtime_options.drop_privileges

    @drop_privileges.setter
    def drop_privileges(self, bool value):
        self.__runtime_options.drop_privileges = value

    @property
    def drop_priv_user(self):
        return self.__runtime_options.drop_priv_user

    @drop_priv_user.setter
    def drop_priv_user(self, value):
        self.__py_encoded_drop_priv_user = value.encode('utf-8')
        self.__runtime_options.drop_priv_user = self.__py_encoded_drop_priv_user

    @property
    def drop_priv_group(self):
        return self.__runtime_options.drop_priv_group

    @drop_priv_group.setter
    def drop_priv_group(self, value):
        self.__py_encoded_drop_priv_group = value.encode('utf-8')
        self.__runtime_options.drop_priv_group = self.__py_encoded_drop_priv_group

cdef class RGBMatrix(Canvas):
    def __cinit__(self, int rows = 0, int chains = 0, int parallel = 0,
        RGBMatrixOptions options = None):

        # If RGBMatrixOptions not provided, create defaults and set any optional
        # parameters supplied
        if options is None:
            options = RGBMatrixOptions()

        if rows > 0:
            options.rows = rows
        if chains > 0:
            options.chain_length = chains
        if parallel > 0:
            options.parallel = parallel

        self.__matrix = cppinc.CreateMatrixFromOptions(options.__options,
            options.__runtime_options)

        if self.__matrix == NULL:
            raise RuntimeError("Failed to create RGBMatrix")

    def __dealloc__(self):
        if self.__matrix != NULL:
            self.__matrix.Clear()
            del self.__matrix
            self.__matrix = NULL

    cdef cppinc.Canvas* _getCanvas(self) except *:
        if <void*>self.__matrix != NULL:
            return self.__matrix
        raise RuntimeError("Canvas was destroyed or not initialized, you cannot use this object anymore")

    def Fill(self, uint8_t red, uint8_t green, uint8_t blue):
        self.__matrix.Fill(red, green, blue)

    def SetPixel(self, int x, int y, uint8_t red, uint8_t green, uint8_t blue):
        self.__matrix.SetPixel(x, y, red, green, blue)

    def Clear(self):
        self.__matrix.Clear()

    def CreateFrameCanvas(self):
        return __createFrameCanvas(self.__matrix.CreateFrameCanvas())

    # The optional "framerate_fraction" parameter allows to choose which
    # multiple of the global frame-count to use. So it slows down your animation
    # to an exact integer fraction of the refresh rate.
    # Default is 1, so immediately next available frame.
    # (Say you have 140Hz refresh rate, then a value of 5 would give you an
    # 28Hz animation, nicely locked to the refresh-rate).
    # If you combine this with RGBMatrixOptions.limit_refresh_rate_hz you can create
    # time-correct animations.
    def SwapOnVSync(self, FrameCanvas newFrame, uint8_t framerate_fraction = 1):
        return __createFrameCanvas(self.__matrix.SwapOnVSync(newFrame.__canvas, framerate_fraction))

    @property
    def luminanceCorrect(self):
        return self.__matrix.luminance_correct()

    @luminanceCorrect.setter
    def luminanceCorrect(self, luminanceCorrect):
        self.__matrix.set_luminance_correct(luminanceCorrect)

    @property
    def pwmBits(self):
        return self.__matrix.pwmbits()

    @pwmBits.setter
    def pwmBits(self, pwmBits):
        self.__matrix.SetPWMBits(pwmBits)

    @property
    def brightness(self):
        return self.__matrix.brightness()

    @brightness.setter
    def brightness(self, brightness):
        self.__matrix.SetBrightness(brightness)

    @property
    def height(self):
        return self.__matrix.height()

    @property
    def width(self):
        return self.__matrix.width()

cdef __createFrameCanvas(cppinc.FrameCanvas* newCanvas):
    canvas = FrameCanvas()
    canvas.__canvas = newCanvas
    return canvas

# Local Variables:
# mode: python
# End:
