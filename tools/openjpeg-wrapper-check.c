/* Standalone guest/host ABI probe, not an ICNS decoder. */
#include <openjpeg.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct { FILE *file; unsigned reads, skips, seeks, messages; } State;
static OPJ_SIZE_T read_cb(void *buffer, OPJ_SIZE_T bytes, void *ctx) {
    State *s = ctx; s->reads++;
    size_t n = fread(buffer, 1, bytes, s->file);
    return n ? n : (OPJ_SIZE_T)-1;
}
static OPJ_OFF_T skip_cb(OPJ_OFF_T bytes, void *ctx) {
    State *s = ctx; s->skips++;
    return fseek(s->file, bytes, SEEK_CUR) ? -1 : bytes;
}
static OPJ_BOOL seek_cb(OPJ_OFF_T offset, void *ctx) {
    State *s = ctx; s->seeks++;
    return fseek(s->file, offset, SEEK_SET) == 0;
}
static void msg_cb(const char *message, void *ctx) {
    State *s = ctx; (void)message; s->messages++;
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    State s = {0}; s.file = fopen(argv[1], "rb");
    if (!s.file || fseek(s.file, 0, SEEK_END)) return 2;
    long length = ftell(s.file); rewind(s.file);
    opj_dparameters_t params; opj_set_default_decoder_parameters(&params);
    opj_codec_t *codec = opj_create_decompress(OPJ_CODEC_JP2);
    opj_stream_t *stream = opj_stream_create(1024, OPJ_TRUE);
    opj_image_t *image = NULL; int ok = 0;
    if (!codec || !stream || length <= 0) goto done;
    opj_set_info_handler(codec, msg_cb, &s);
    opj_set_warning_handler(codec, msg_cb, &s);
    opj_set_error_handler(codec, msg_cb, &s);
    opj_stream_set_user_data(stream, &s, NULL);
    opj_stream_set_user_data_length(stream, length);
    opj_stream_set_read_function(stream, read_cb);
    opj_stream_set_skip_function(stream, skip_cb);
    opj_stream_set_seek_function(stream, seek_cb);
    if (!opj_setup_decoder(codec, &params) || !opj_read_header(stream, codec, &image) ||
        !opj_decode(codec, stream, image) || !opj_end_decompress(codec, stream)) goto done;
    if (image->numcomps != 3 || image->x1 != 16 || image->y1 != 16) goto done;
    for (int c = 0; c < 3; c++) {
        if (!image->comps[c].data || image->comps[c].w != 16 || image->comps[c].h != 16) goto done;
        for (int i = 0; i < 256; i++)
            if (image->comps[c].data[i] != (c == 0 ? 17 : c == 1 ? 83 : 191)) goto done;
    }
    /* The JP2 decoder may seek rather than use the optional skip callback. */
    ok = s.reads && s.seeks && s.messages;
done:
    printf("OPENJPEG_ABI %s reads=%u skips=%u seeks=%u messages=%u\n", ok ? "PASS" : "FAIL", s.reads, s.skips, s.seeks, s.messages);
    if (image) opj_image_destroy(image);
    if (stream) opj_stream_destroy(stream);
    if (codec) opj_destroy_codec(codec);
    if (s.file) fclose(s.file);
    return ok ? 0 : 1;
}
