#pragma once

class parser;

class interpreter {
    friend class parser;

public:
    interpreter();
    void execute();

private:
    void cmd_text();
    void cmd_cleartext();
    void cmd_bgload();
    void cmd_setimg();
    void cmd_sound();
    void cmd_music();
    void cmd_choice();
    void cmd_setvar();
    void cmd_gsetvar();
    void cmd_if();
    void cmd_fi();
    void cmd_random();
    void cmd_label();
    void cmd_goto();
    void cmd_jump();
    void cmd_delay();
    void cmd_endscript();
    void cmd_autoline();
};