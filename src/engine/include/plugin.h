#ifndef SG_PLUGIN_H
#define SG_PLUGIN_H

#include "audio/paifx.h"
#include "audiodsp/lib/peak_meter.h"
#include "compiler.h"
#include "ds/list.h"

#define EVENT_NOTEON     0
#define EVENT_NOTEOFF    1
#define EVENT_PITCHBEND  2
#define EVENT_CONTROLLER 3
#define EVENT_AUTOMATION 4

typedef void (*fp_queue_message)(char*, char*);

typedef SGFLT PluginData;

typedef int PluginPortDescriptor;


typedef struct _PluginPortRangeHint {
  PluginData DefaultValue;
  PluginData LowerBound;
  PluginData UpperBound;
} PluginPortRangeHint;

typedef void * PluginHandle;

// MIDI event
typedef struct {
    int type;
    int tick;
    unsigned int tv_sec;
    unsigned int tv_nsec;
    int channel;
    int note;
    int velocity;
    int duration;

    int param;
    SGFLT value;
    SGFLT start;
    SGFLT length;
    int port;
} t_seq_event;

typedef struct {
    int uid;
    SGFLT* samples[2];
    SGFLT ratio_orig;
    SGFLT volume;  // Linear volume, not dB
    int channels;
    int length;
    SGFLT sample_rate;
    // audio files are loaded dynamically when they are first seen
    // in the project
    int is_loaded;
    // host sample-rate, cached here for easy access
    SGFLT host_sr;
    t_file_fx_controls fx_controls;
    char path[2048];
} t_audio_pool_item;

typedef t_audio_pool_item * (*fp_get_audio_pool_item_from_host)(int);

/* For sorting a list by start time */
int seq_event_cmpfunc(void *self, void *other);

/* Descriptor for a Type of Plugin:

   This structure is used to describe a plugin type. It provides a
   number of functions to examine the type, instantiate it, link it to
   buffers and workspaces and to run it. */

typedef struct _PluginDescriptor {
    char pad1[CACHE_LINE_SIZE];
    int PortCount;

    PluginPortDescriptor * PortDescriptors;

    // This member indicates an array of range hints for each port (see
    // above). Valid indices vary from 0 to PortCount-1.
    PluginPortRangeHint * PortRangeHints;

    PluginHandle (*instantiate)(
        struct _PluginDescriptor * Descriptor,
        int SampleRate,
        fp_get_audio_pool_item_from_host a_host_audio_pool_func,
        int a_plugin_uid,
        fp_queue_message
    );

    void (*connect_port)(
        PluginHandle Instance,
        int Port,
        PluginData * DataLocation
    );

    // Assign the audio buffer at DataLocation to index a_index
    void (*connect_buffer)(
        PluginHandle Instance,
        int a_index,
        SGFLT* DataLocation,
        int a_is_sidechain
    );

    void (*cleanup)(PluginHandle Instance);

    // Load the plugin state file at a_file_path
    void (*load)(
        PluginHandle Instance,
        struct _PluginDescriptor * Descriptor,
        char * a_file_path
    );

    void (*set_port_value)(PluginHandle Instance, int a_port, SGFLT a_value);

    void (*set_cc_map)(PluginHandle Instance, char * a_msg);

    /* When a panic message is sent, do whatever it takes to fix any stuck
     notes. */
    void (*panic)(PluginHandle Instance);

    //For now all plugins must set it to 1.

    int API_Version;

    void (*configure)(
        PluginHandle Instance,
        char *Key,
        char *Value,
        pthread_spinlock_t * a_spinlock
    );

    // Plugins NOT part of a send channel will always call this
    void (*run_replacing)(
        PluginHandle Instance,
        int SampleCount,
        struct ShdsList* midi_events,
        struct ShdsList* atm_events
    );

    // Plugins that are part of a send channel will always call this,
    // any plugin that isn't a fader/channel type plugin do not need
    // to implement or set this
    void (*run_mixing)(
        PluginHandle Instance,
        int SampleCount,
        SGFLT** output_buffers,
        int output_count,
        struct ShdsList* midi_events,
        struct ShdsList* atm_events,
        t_pkm_peak_meter* peak_meter
    );

    /* Do anything like warming up oscillators, etc...  in preparation
     * for offline rendering.  This must be called after loading
     * the project.
     */
    void (*offline_render_prep)(PluginHandle Instance, SGFLT sample_rate);

    /* Force any notes to off, etc...  and anything else you may want to
     * do when the transport stops
     */
    void (*on_stop)(PluginHandle Instance);

    char pad2[CACHE_LINE_SIZE];
} PluginDescriptor;

typedef PluginDescriptor* (*PluginDescriptor_Function)();

typedef struct {
    int type;
    int tick;
    SGFLT value;
    int port;
} t_plugin_event_queue_item;

typedef struct {
    int count;
    int pos;
    t_plugin_event_queue_item items[200];
} t_plugin_event_queue;

typedef struct {
    int count;
    int ports[5];
    SGFLT lows[5];
    SGFLT highs[5];
} t_cc_mapping;

typedef struct {
    t_cc_mapping map[128];
} t_plugin_cc_map;

typedef struct {
    char pad1[CACHE_LINE_SIZE];
    int active;
    int power;
    PluginDescriptor *descriptor;
    PluginHandle plugin_handle;
    int uid;
    int pool_uid;
    int atm_count;
    t_seq_event * atm_buffer;
    struct ShdsList * atm_list;
    PluginDescriptor_Function descfn;
    int mute;
    int solo;
    char pad2[CACHE_LINE_SIZE];
} t_plugin;

//PluginDescriptor_Function PLUGIN_DESC_FUNCS[];

void v_plugin_event_queue_add(t_plugin_event_queue*, int, int, SGFLT, int);
void v_plugin_event_queue_reset(t_plugin_event_queue*);
t_plugin_event_queue_item * v_plugin_event_queue_iter(
    t_plugin_event_queue*, int);
void v_plugin_event_queue_atm_set(t_plugin_event_queue*, int, SGFLT*);
SGFLT f_cc_to_ctrl_val(PluginDescriptor*, int, SGFLT);
void v_cc_mapping_init(t_cc_mapping*);
void v_cc_map_init(t_plugin_cc_map*);
void v_cc_map_translate(
    t_plugin_cc_map*,
    PluginDescriptor*,
    SGFLT*,
    int,
    SGFLT
);
void v_generic_cc_map_set(t_plugin_cc_map*, char*);
void v_ev_clear(t_seq_event * a_event);
void v_ev_set_atm(
    t_seq_event* a_event,
    int a_port_num,
    int a_value
);
SGFLT * g_get_port_table(
    PluginHandle * handle,
    PluginDescriptor * descriptor
);
void generic_file_loader(
    PluginHandle Instance,
    PluginDescriptor * Descriptor,
    char * a_path,
    SGFLT * a_table,
    t_plugin_cc_map * a_cc_map
);
void set_pyfx_port(
    PluginDescriptor * a_desc,
    int a_port,
    SGFLT a_default,
    SGFLT a_min,
    SGFLT a_max
);
PluginDescriptor * get_pyfx_descriptor(int a_port_count);
SGFLT f_atm_to_ctrl_val(
    PluginDescriptor *self,
    int a_port,
    SGFLT a_val
);
void v_ev_set_pitchbend(
    t_seq_event* a_event,
    int a_channel,
    int a_value
);
void v_ev_set_controller(
    t_seq_event* a_event,
    int a_channel,
    int a_cc_num,
    int a_value
);
void v_ev_set_noteon(
    t_seq_event* a_event,
    int a_channel,
    int a_note,
    int a_velocity
);
void v_ev_set_noteoff(
    t_seq_event* a_event,
    int a_channel,
    int a_note,
    int a_velocity
);

NO_OPTIMIZATION void g_plugin_init(
    t_plugin * f_result,
    int a_sample_rate,
    int a_index,
    fp_get_audio_pool_item_from_host a_host_audio_pool_func,
    int a_plugin_uid,
    fp_queue_message a_queue_func
);

#endif
