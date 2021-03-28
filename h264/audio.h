int32_t audioplay_create (ILCLIENT_T* client, COMPONENT_T** audio_render, COMPONENT_T** list, int listindex);
int32_t audioplay_delete (COMPONENT_T* audio_render);
int32_t audioplay_play_buffer (COMPONENT_T* audio_render, uint8_t* buffer, uint32_t length);
int32_t audioplay_set_dest (COMPONENT_T* audio_render, const char* name);
uint32_t audioplay_get_latency (COMPONENT_T* audio_render);
