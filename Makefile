all: build-debug

build-release:
	CARGO_HOME="${HOME}/.cargo" cargo build --release
	cp target/release/trading-game-server trading-game-server

build-debug:
	CARGO_HOME="${HOME}/.cargo" cargo build
	cp target/debug/trading-game-server trading-game-server

clean:
	rm -rf target
	rm -f trading-game-server

.PHONY: all build-debug build-release clean
