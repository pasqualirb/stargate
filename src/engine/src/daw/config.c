#include <stdlib.h>
#include <string.h>

#include "stargate.h"
#include "csv/1d.h"
#include "csv/kvp.h"
#include "csv/split.h"
#include "daw.h"
#include "daw/config.h"
#include "files.h"
#include "osc.h"


void v_daw_configure(const char* a_key, const char* a_value){
    char buf[1024];
    t_daw* self = DAW;
    log_info("v_daw_configure:  key: \"%s\", value: \"%s\"", a_key, a_value);

    if(!strcmp(a_key, DN_CONFIGURE_KEY_NOTE_ON)){
        a_value = str_split(a_value, buf, '|');
        int rack_num = atoi(buf);
        a_value = str_split(a_value, buf, '|');
        int note = atoi(buf);
        pthread_spin_lock(&STARGATE->main_lock);
        t_seq_event* ev = &QWERTY_MIDI.events[QWERTY_MIDI.event_count];
        ev->note = note;
        ev->tick = 0;
        ev->type = EVENT_NOTEON;
        ev->velocity = 100;
        QWERTY_MIDI.rack_num = rack_num;
        ++QWERTY_MIDI.event_count;
        pthread_spin_unlock(&STARGATE->main_lock);
    } else if(!strcmp(a_key, DN_CONFIGURE_KEY_NOTE_OFF)){
        a_value = str_split(a_value, buf, '|');
        int rack_num = atoi(buf);
        a_value = str_split(a_value, buf, '|');
        int note = atoi(buf);
        pthread_spin_lock(&STARGATE->main_lock);
        t_seq_event* ev = &QWERTY_MIDI.events[QWERTY_MIDI.event_count];
        ev->note = note;
        ev->tick = 0;
        ev->type = EVENT_NOTEOFF;
        ev->velocity = 0;
        QWERTY_MIDI.rack_num = rack_num;
        ++QWERTY_MIDI.event_count;
        pthread_spin_unlock(&STARGATE->main_lock);
    } else if(!strcmp(a_key, DN_CONFIGURE_KEY_PER_FILE_FX)){
        a_value = str_split(a_value, buf, '|');
        int ap_uid = atoi(buf);
        a_value = str_split(a_value, buf, '|');
        int port_num = atoi(buf);
        a_value = str_split(a_value, buf, '|');
        SGFLT port_val = atof(buf);

        v_daw_papifx_set_control(
            ap_uid,
            port_num,
            port_val
        );
    } else if(!strcmp(a_key, DN_CONFIGURE_KEY_PER_FILE_FX_PASTE)){
       papifx_paste(a_value);
    } else if(!strcmp(a_key, DN_CONFIGURE_KEY_PER_FILE_FX_CLEAR)){
        int ap_uid = atoi(a_value);
        t_audio_pool_item* item = &STARGATE->audio_pool->items[ap_uid];
        pthread_spin_lock(&STARGATE->main_lock);
        papifx_reset(&item->fx_controls);
        pthread_spin_unlock(&STARGATE->main_lock);
    } else if(!strcmp(a_key, DN_CONFIGURE_KEY_PER_AUDIO_ITEM_FX)){
        a_value = str_split(a_value, buf, '|');
        int f_item_index = atoi(buf);
        a_value = str_split(a_value, buf, '|');
        int f_audio_item_index = atoi(buf);
        a_value = str_split(a_value, buf, '|');
        int f_port_num = atoi(buf);
        a_value = str_split(a_value, buf, '|');
        SGFLT f_port_val = atof(buf);

        v_daw_paif_set_control(
            self,
            f_item_index,
            f_audio_item_index,
            f_port_num,
            f_port_val
        );
    } else if(!strcmp(a_key, DN_CONFIGURE_KEY_DN_PLAYBACK)) {
        a_value = str_split(a_value, buf, '|');
        int f_mode = atoi(buf);
        sg_assert(
            f_mode >= 0 && f_mode <= 2,
            "v_daw_configure: DN_CONFIGURE_KEY_DN_PLAYBACK invalid mode: %i",
            f_mode
        );
        a_value = str_split(a_value, buf, '|');
        double f_beat = atof(buf);
        v_daw_set_playback_mode(self, f_mode, f_beat, 1);
    } else if(!strcmp(a_key, DN_CONFIGURE_KEY_CS)) {
        // Change the active sequence being played
        //Ensure that a project isn't being loaded right now
        pthread_spin_lock(&STARGATE->main_lock);
        pthread_spin_unlock(&STARGATE->main_lock);
        // TODO: assert that the project is not playing
        int uid = atoi(a_value);
        daw_set_sequence(self, uid);
    } else if(!strcmp(a_key, DN_CONFIGURE_KEY_NS)) {
        // new sequence
        //Ensure that a project isn't being loaded right now
        pthread_spin_lock(&STARGATE->main_lock);
        pthread_spin_unlock(&STARGATE->main_lock);

        int uid = atoi(a_value);
        sg_assert(
            uid >= 0 && uid < DAW_MAX_SONG_COUNT,
            "v_daw_configure: DN_CONFIGURE_KEY_NS uid %i out of range 0 to %i",
            uid,
            DAW_MAX_SONG_COUNT
        );
        t_daw_sequence * f_result = g_daw_sequence_get(self, uid);
        // Should not already be set
        sg_assert(
            !self->seq_pool[uid],
            "v_daw_configure: DN_CONFIGURE_KEY_NS seq already set"
        );

        pthread_spin_lock(&STARGATE->main_lock);
        self->seq_pool[uid] = f_result;
        pthread_spin_unlock(&STARGATE->main_lock);
    } else if(!strcmp(a_key, DN_CONFIGURE_KEY_SR)) {
        // save sequence (reload after save)
        //Ensure that a project isn't being loaded right now
        pthread_spin_lock(&STARGATE->main_lock);
        pthread_spin_unlock(&STARGATE->main_lock);

        int uid = atoi(a_value);
        sg_assert(
            uid >= 0 && uid < DAW_MAX_SONG_COUNT,
            "v_daw_configure: DN_CONFIGURE_KEY_SR uid %i out of range 0 to %i",
            uid,
            DAW_MAX_SONG_COUNT
        );
        t_daw_sequence * f_result = g_daw_sequence_get(self, uid);

        // It is assumed that the current sequence is the only sequence that
        // can be edited.  Ensure that is the case.
        sg_assert(
            self->en_song->sequences == self->seq_pool[uid],
            "v_daw_configure: DN_CONFIGURE_KEY_SR not editing current song"
        );
        t_daw_sequence * f_old_sequence = NULL;
        f_old_sequence = self->en_song->sequences;

        pthread_spin_lock(&STARGATE->main_lock);
        self->seq_pool[uid] = f_result;
        self->en_song->sequences = f_result;
        pthread_spin_unlock(&STARGATE->main_lock);

        // TODO: A real free function for this
        if(f_old_sequence){
            free(f_old_sequence);
        }
    } else if(!strcmp(a_key, DN_CONFIGURE_KEY_SI)) {
        //Save Item
        pthread_spin_lock(&STARGATE->main_lock);
        g_daw_item_get(self, atoi(a_value));
        pthread_spin_unlock(&STARGATE->main_lock);
    } else if(!strcmp(a_key, DN_CONFIGURE_KEY_SAVE_ATM)){
        t_daw_atm_sequence * f_result = g_daw_atm_sequence_get(self);

        t_daw_atm_sequence * f_old_sequence = NULL;
        if(self->en_song->sequences_atm)
        {
            f_old_sequence = self->en_song->sequences_atm;
        }
        pthread_spin_lock(&STARGATE->main_lock);
        self->en_song->sequences_atm = f_result;
        pthread_spin_unlock(&STARGATE->main_lock);
        if(f_old_sequence)
        {
            v_daw_atm_sequence_free(f_old_sequence);
        }
    }
    else if(!strcmp(a_key, DN_CONFIGURE_KEY_LOOP)) //Set loop mode
    {
        int f_value = atoi(a_value);

        pthread_spin_lock(&STARGATE->main_lock);
        v_daw_set_loop_mode(self, f_value);
        pthread_spin_unlock(&STARGATE->main_lock);
    }
    else if(!strcmp(a_key, DN_CONFIGURE_KEY_OS)) //Open Song
    {
        t_key_value_pair * f_kvp = g_kvp_get(a_value);
        int f_first_open = atoi(f_kvp->key);

        pthread_spin_lock(&STARGATE->main_lock);
        STARGATE->is_offline_rendering = 1;
        pthread_spin_unlock(&STARGATE->main_lock);

        v_daw_open_project(f_first_open);

        pthread_spin_lock(&STARGATE->main_lock);
        STARGATE->is_offline_rendering = 0;
        pthread_spin_unlock(&STARGATE->main_lock);
    } else if(!strcmp(a_key, DN_CONFIGURE_KEY_SOLO)){ //Set track solo
        a_value = str_split(a_value, buf, '|');
        int f_track_num = atoi(buf);
        a_value = str_split(a_value, buf, '|');
        int f_mode = atoi(buf);
        sg_assert(
            f_mode == 0 || f_mode == 1,
            "v_daw_configure: DN_CONFIGURE_KEY_SOLO invalid mode: %i",
            f_mode
        );

        pthread_spin_lock(&STARGATE->main_lock);

        self->track_pool[f_track_num]->solo = f_mode;
        //self->track_pool[f_track_num]->period_event_index = 0;

        v_daw_set_is_soloed(self);

        pthread_spin_unlock(&STARGATE->main_lock);
    } else if(!strcmp(a_key, DN_CONFIGURE_KEY_MUTE)){
        a_value = str_split(a_value, buf, '|');
        int f_track_num = atoi(buf);
        a_value = str_split(a_value, buf, '|');
        int f_mode = atoi(buf);
        sg_assert(
            f_mode == 0 || f_mode == 1,
            "v_daw_configure: DN_CONFIGURE_KEY_MUTE invalid mode: %i",
            f_mode
        );
        pthread_spin_lock(&STARGATE->main_lock);

        self->track_pool[f_track_num]->mute = f_mode;
        //self->track_pool[f_track_num]->period_event_index = 0;

        pthread_spin_unlock(&STARGATE->main_lock);
    } else if(!strcmp(a_key, DN_CONFIGURE_KEY_PLUGIN_INDEX)){
        a_value = str_split(a_value, buf, '|');
        int f_track_num = atoi(buf);
        a_value = str_split(a_value, buf, '|');
        int f_index = atoi(buf);
        a_value = str_split(a_value, buf, '|');
        int f_plugin_index = atoi(buf);
        a_value = str_split(a_value, buf, '|');
        int f_plugin_uid = atoi(buf);
        a_value = str_split(a_value, buf, '|');
        int f_power = atoi(buf);

        t_pytrack * f_track = DAW->track_pool[f_track_num];

        v_set_plugin_index(
            f_track,
            f_index,
            f_plugin_index,
            f_plugin_uid,
            f_power,
            1
        );
    }
    else if(!strcmp(a_key, DN_CONFIGURE_KEY_UPDATE_SEND))
    {
        v_daw_update_track_send(self, 1);
    }
    else if(!strcmp(a_key, DN_CONFIGURE_KEY_AUDIO_INPUTS))
    {
        v_daw_update_audio_inputs();
    }
    else if(!strcmp(a_key, DN_CONFIGURE_KEY_SET_OVERDUB_MODE))
    {
        int f_bool = atoi(a_value);
        sg_assert(
            f_bool == 0 || f_bool == 1,
            "v_daw_configure: DN_CONFIGURE_KEY_SET_OVERDUB_MODE "
            "invalid value %i",
            f_bool
        );
        pthread_spin_lock(&STARGATE->main_lock);
        self->overdub_mode = f_bool;
        pthread_spin_unlock(&STARGATE->main_lock);
    }
    else if(!strcmp(a_key, DN_CONFIGURE_KEY_PANIC))
    {
        pthread_spin_lock(&STARGATE->main_lock);
        STARGATE->is_offline_rendering = 1;
        pthread_spin_unlock(&STARGATE->main_lock);

        v_daw_panic(self);

        pthread_spin_lock(&STARGATE->main_lock);
        STARGATE->is_offline_rendering = 0;
        pthread_spin_unlock(&STARGATE->main_lock);

    }
    else if(!strcmp(a_key, DN_CONFIGURE_KEY_SET_POS))
    {
        if(STARGATE->playback_mode != 0)
        {
            return;
        }

        double f_beat = atof(a_value);

        pthread_spin_lock(&STARGATE->main_lock);
        v_daw_set_playback_cursor(self, f_beat);
        pthread_spin_unlock(&STARGATE->main_lock);
    }
    else if(!strcmp(a_key, DN_CONFIGURE_KEY_MIDI_DEVICE))
    {
#ifndef NO_MIDI
        t_line_split * f_val_arr = g_split_line('|', a_value);
        int f_on = atoi(f_val_arr->str_arr[0]);
        int f_device = atoi(f_val_arr->str_arr[1]);
        int f_output = atoi(f_val_arr->str_arr[2]);
        v_free_split_line(f_val_arr);

        pthread_spin_lock(&STARGATE->main_lock);

        v_daw_set_midi_device(f_on, f_device, f_output);

        pthread_spin_unlock(&STARGATE->main_lock);
#endif
    }
    else
    {
        log_info(
            "Unknown configure message key: %s, value %s",
            a_key,
            a_value
        );
    }
}

void v_daw_osc_send(t_osc_send_data * a_buffers){
    int f_i;
    t_pkm_peak_meter * f_pkm;

    a_buffers->f_tmp1[0] = '\0';
    a_buffers->f_tmp2[0] = '\0';

    f_pkm = DAW->track_pool[0]->peak_meter;
    sprintf(
        a_buffers->f_tmp2,
        "%i:%f:%f",
        0,
        f_pkm->value[0],
        f_pkm->value[1]
    );
    v_pkm_reset(f_pkm);

    for(f_i = 1; f_i < DN_TRACK_COUNT; ++f_i){
        f_pkm = DAW->track_pool[f_i]->peak_meter;
        if(!f_pkm->dirty){  //has ran since last v_pkm_reset())
            sprintf(
                a_buffers->f_tmp1,
                "|%i:%f:%f",
                f_i,
                f_pkm->value[0],
                f_pkm->value[1]
            );
            v_pkm_reset(f_pkm);
            strcat(a_buffers->f_tmp2, a_buffers->f_tmp1);
        }
    }

    v_queue_osc_message("peak", a_buffers->f_tmp2);

    a_buffers->f_tmp1[0] = '\0';
    a_buffers->f_tmp2[0] = '\0';

    if(
        STARGATE->playback_mode > 0
        &&
        !STARGATE->is_offline_rendering
    ){
        sprintf(
            a_buffers->f_msg,
            "%f",
            DAW->ts[0].ml_current_beat
        );
        v_queue_osc_message("cur", a_buffers->f_msg);
    }

    if(STARGATE->osc_queue_index > 0){
        for(f_i = 0; f_i < STARGATE->osc_queue_index; ++f_i){
            strcpy(
                a_buffers->osc_queue_keys[f_i],
                STARGATE->osc_queue_keys[f_i]
            );
            strcpy(
                a_buffers->osc_queue_vals[f_i],
                STARGATE->osc_queue_vals[f_i]
            );
        }

        pthread_spin_lock(&STARGATE->main_lock);

        //Now grab any that may have been written since the previous copy

        for(;f_i < STARGATE->osc_queue_index; ++f_i){
            strcpy(
                a_buffers->osc_queue_keys[f_i],
                STARGATE->osc_queue_keys[f_i]
            );
            strcpy(
                a_buffers->osc_queue_vals[f_i],
                STARGATE->osc_queue_vals[f_i]
            );
        }

        int f_index = STARGATE->osc_queue_index;
        STARGATE->osc_queue_index = 0;

        pthread_spin_unlock(&STARGATE->main_lock);

        if(!STARGATE->is_offline_rendering){
            for(f_i = 0; f_i < f_index; ++f_i){
                sprintf(
                    a_buffers->f_tmp1,
                    "%s|%s\n",
                    a_buffers->osc_queue_keys[f_i],
                    a_buffers->osc_queue_vals[f_i]
                );
                v_ui_send("stargate/daw", a_buffers->f_tmp1);
            }
        }
    }
}


