"""Compile board initialization against GPIO probes; never drive host hardware."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("xiao,external", [(False, False), (True, False), (True, True)])
def test_board_antenna_selection_is_explicit_and_generic_touches_no_gpio(
    tmp_path, xiao, external
):
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("C compiler unavailable")
    (tmp_path / "sdkconfig.h").write_text(
        f"#define CONFIG_CSI_BOARD_XIAO_ESP32C6 {int(xiao)}\n"
        f"#define CONFIG_CSI_XIAO_EXTERNAL_ANTENNA {int(external)}\n"
    )
    (tmp_path / "driver").mkdir()
    (tmp_path / "freertos").mkdir()
    (tmp_path / "driver/gpio.h").write_text("""
#define GPIO_NUM_3 3
#define GPIO_NUM_14 14
#define GPIO_MODE_OUTPUT 1
int gpio_set_direction(int pin, int mode);
int gpio_set_level(int pin, int level);
""")
    (tmp_path / "esp_err.h").write_text(
        "#include <assert.h>\n#define ESP_ERROR_CHECK(v) assert((v)==0)\n"
    )
    (tmp_path / "freertos/FreeRTOS.h").write_text("#define pdMS_TO_TICKS(v) (v)\n")
    (tmp_path / "freertos/task.h").write_text("void vTaskDelay(unsigned ticks);\n")
    source = tmp_path / "board.c"
    source.write_text(
        """
#include <assert.h>
#include <string.h>
#include "radio_board.h"
static unsigned directions, writes, delay;
static int pins[2], levels[2];
int gpio_set_direction(int pin, int mode) { ++directions; return 0; }
int gpio_set_level(int pin, int level) {
    assert(writes<2); pins[writes]=pin; levels[writes++]=level; return 0;
}
void vTaskDelay(unsigned ticks) { delay += ticks; }
int main(void) {
    csi_board_init();
    if (IS_XIAO) {
        assert(directions==2 && writes==2 && delay==100);
        assert(pins[0]==3 && levels[0]==0);
        assert(pins[1]==14 && levels[1]==IS_EXTERNAL);
        assert(!strcmp(csi_board_name(), "xiao_esp32c6"));
        assert(!strcmp(csi_board_antenna(), IS_EXTERNAL ? "external" : "builtin"));
    } else {
        assert(directions==0 && writes==0 && delay==0);
        assert(!strcmp(csi_board_name(), "generic"));
        assert(!strcmp(csi_board_antenna(), "board_default"));
    }
}
""".replace("IS_XIAO", str(int(xiao))).replace("IS_EXTERNAL", str(int(external)))
    )
    executable = tmp_path / "board"
    root = Path("src/firmware/radio/common")
    subprocess.run(
        [
            compiler,
            "-std=c11",
            "-I",
            str(tmp_path),
            "-I",
            str(root / "include"),
            str(source),
            str(root / "radio_board.c"),
            "-o",
            str(executable),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run([str(executable)], check=True, capture_output=True)
