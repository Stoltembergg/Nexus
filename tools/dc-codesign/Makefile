CC ?= cc
CFLAGS ?= -D_GNU_SOURCE -O2 -g -Wall -Wextra -std=c11 -Wno-deprecated-declarations
LDLIBS ?= -lcrypto

BIN := dc-codesign
SRC := main.c dc_codesign.c

.PHONY: all clean test

all: $(BIN)

$(BIN): $(SRC) dc_codesign.h
	$(CC) $(CFLAGS) -o $@ $(SRC) $(LDLIBS)

test: $(BIN)
	./test.sh

clean:
	rm -f $(BIN)
