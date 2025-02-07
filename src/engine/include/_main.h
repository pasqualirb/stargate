#ifndef MAIN_H
#define MAIN_H

#include "compiler.h"
#include "hardware/config.h"


#define CLOCKID CLOCK_REALTIME
#define SIG SIGRTMIN

int _main(int argc, char** argv);
void start_osc_thread();
void start_ui_thread(int pid);
void setup_signal_handling();

int v_configure(
    char* path,
    char* key,
    char* value
);
int daw_render(int argc, char** argv);
void print_help();
int main_loop();
void v_run_main_loop(
    int sample_count,
    SGFLT **output,
    SGFLT *a_input_buffers
);
void set_thread_params();
void alloc_output_buffers();
int init_hardware(
    struct HardwareConfig* hardware_config
);
int start_engine(char* project_dir);
void stop_engine();
#endif
