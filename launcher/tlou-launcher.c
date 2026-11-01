/* TLOU Launcher.exe: opens the game launcher (tlou_launcher.pyw) from its own folder. No console
 * window. Python comes from the PATH: the game's preparation scripts need it anyway. Extra
 * arguments are passed on. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdlib.h>
#include <wchar.h>

#define TITLE L"The Last of Us Remastered"
#define FAILED_WITHIN_MS 4000

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR arguments, int show)
{
    (void)instance, (void)previous, (void)show;
    static wchar_t dir[32768], script[32768], line[32768], shell[MAX_PATH];
    DWORD length = GetModuleFileNameW(NULL, dir, 32768);
    if (length == 0 || length >= 32768)
        return 1;
    wchar_t *slash = wcsrchr(dir, L'\\');
    if (slash)
        *slash = 0;
    swprintf(script, 32768, L"%ls\\tlou_launcher.pyw", dir);
    if (GetFileAttributesW(script) == INVALID_FILE_ATTRIBUTES) {
        MessageBoxW(NULL, L"tlou_launcher.pyw n\u00e3o foi encontrado ao lado deste arquivo.", TITLE,
                    MB_OK | MB_ICONERROR);
        return 1;
    }
    /* Through cmd.exe: a version manager's pythonw on the PATH may be a batch file. */
    if (!GetEnvironmentVariableW(L"ComSpec", shell, MAX_PATH))
        wcscpy(shell, L"C:\\Windows\\System32\\cmd.exe");
    swprintf(line, 32768, L"\"%ls\" /c pythonw \"tlou_launcher.pyw\"%ls%ls", shell,
             arguments && *arguments ? L" " : L"", arguments ? arguments : L"");

    STARTUPINFOW startup = {.cb = sizeof(startup)};
    PROCESS_INFORMATION process;
    DWORD code = 1;
    BOOL started = CreateProcessW(shell, line, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, dir, &startup, &process);
    if (started) {
        CloseHandle(process.hThread);
        /* Still running: the launcher is open. Gone with an error: it never opened. */
        if (WaitForSingleObject(process.hProcess, FAILED_WITHIN_MS) == WAIT_TIMEOUT)
            code = 0;
        else
            GetExitCodeProcess(process.hProcess, &code);
        CloseHandle(process.hProcess);
    }
    if (!started || code != 0) {
        MessageBoxW(NULL, L"O launcher n\u00e3o abriu. Confira se o Python est\u00e1 instalado e no PATH.", TITLE,
                    MB_OK | MB_ICONERROR);
        return 1;
    }
    return 0;
}
