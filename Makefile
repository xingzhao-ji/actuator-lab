PYTHON ?= .venv/bin/python
CXX := clang++
CACHE ?= $(HOME)/.cache/actuator-lab
export ACTUATOR_CACHE := $(CACHE)
BUILD := $(CACHE)/build
FLAGS := -std=c++20 -O2 -Wall -Wextra -Werror -Iinclude
CORE := src/model.cpp src/control.cpp src/simulation.cpp
HEADERS := $(wildcard include/actuator/*.hpp)
GUARD := python3 scripts/guard.py
.PHONY: build test sanitize verify plots
build: $(BUILD)/actuator_lab
$(BUILD)/actuator_lab: $(CORE) src/main.cpp $(HEADERS)
	$(GUARD) $(CXX) $(FLAGS) $(CORE) src/main.cpp -o $@
$(BUILD)/%_tests: tests/%_tests.cpp $(CORE) $(HEADERS)
	$(GUARD) $(CXX) $(FLAGS) $(CORE) $< -o $@
test: build $(BUILD)/core_tests $(BUILD)/control_tests $(BUILD)/simulation_tests
	$(GUARD) $(BUILD)/core_tests
	$(GUARD) $(BUILD)/control_tests
	$(GUARD) $(BUILD)/simulation_tests
	$(GUARD) $(PYTHON) -m pytest -q -p no:cacheprovider tests
sanitize:
	$(GUARD) $(CXX) $(FLAGS) -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer $(CORE) tests/core_tests.cpp -o $(BUILD)/core_sanitized
	$(GUARD) $(BUILD)/core_sanitized
	$(GUARD) $(CXX) $(FLAGS) -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer $(CORE) tests/simulation_tests.cpp -o $(BUILD)/simulation_sanitized
	$(GUARD) $(BUILD)/simulation_sanitized
plots:
	$(GUARD) $(PYTHON) scripts/plot_dependencies.py
verify: test sanitize
	$(GUARD) $(PYTHON) python/experiments.py --binary $(BUILD)/actuator_lab --output evidence
	$(GUARD) $(PYTHON) python/report.py evidence
	$(GUARD) $(PYTHON) scripts/manifest.py
