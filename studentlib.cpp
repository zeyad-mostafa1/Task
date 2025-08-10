#include <sqlite3.h>
#include <string.h>
#include <stdio.h>

struct CallbackData {
    char** result_str;
    int* remaining_size;
};

static int callback(void* data, int argc, char** argv, char** azColName) {
    CallbackData* cb_data = static_cast<CallbackData*>(data);
    char* result_str = *cb_data->result_str;
    int remaining_size = *cb_data->remaining_size;

    if (remaining_size <= 0) {
        return 0;
    }

    for (int i = 0; i < argc; i++) {
        int written = snprintf(result_str, remaining_size, "%s: %s\n",
                               azColName[i], argv[i] ? argv[i] : "NULL");
        result_str += written;
        remaining_size -= written;
        if (remaining_size <= 0) break;
    }

    if (remaining_size > 0) {
        int written = snprintf(result_str, remaining_size, "---\n");
        result_str += written;
        remaining_size -= written;
    }

    *cb_data->result_str = result_str;
    *cb_data->remaining_size = remaining_size;

    return 0;
}

extern "C" {
    int search_students(const char* db_path, const char* search_name, char* result_buffer, int buffer_size) {
        sqlite3* db;
        char* zErrMsg = 0;
        int rc;

        rc = sqlite3_open(db_path, &db);
        if (rc != SQLITE_OK) {
            snprintf(result_buffer, buffer_size, "Error opening database: %s", sqlite3_errmsg(db));
            sqlite3_close(db);
            return -1;
        }

        char sql[256];
        snprintf(sql, sizeof(sql), "SELECT id, name, grade, course FROM students WHERE LOWER(name) LIKE LOWER('%%%s%%');", search_name);

        char* result_str = result_buffer;
        int remaining_size = buffer_size;

        CallbackData cb_data = { &result_str, &remaining_size };

        rc = sqlite3_exec(db, sql, callback, &cb_data, &zErrMsg);
        if (rc != SQLITE_OK) {
            snprintf(result_buffer, buffer_size, "SQL error: %s", zErrMsg);
            sqlite3_free(zErrMsg);
            sqlite3_close(db);
            return -1;
        }

        sqlite3_close(db);
        return 0;
    }
}