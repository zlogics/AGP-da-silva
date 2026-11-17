
#Requires AutoHotkey v2.0
#SingleInstance Force

global found := Map()
global monitorData := []

app := Gui("+AlwaysOnTop", "CheckLifting - Gerenciador de Telas")
app.SetFont("s10", "Segoe UI")

app.AddText("w540", "Janelas abertas do CheckLifting:")

global lv := app.AddListView("w650 r10 Grid", ["Tela", "HWND"])
lv.ModifyCol(1, 490)
lv.ModifyCol(2, 130)

btnRefresh := app.AddButton("w120", "Atualizar lista")
btnRefresh.OnEvent("Click", RefreshWindows)

app.AddText("xm y+12", "Mover janela selecionada:")

global monitorDrop := app.AddDropDownList("w350 Choose1", [])
btnMove := app.AddButton("x+10 yp-2 w120", "Mover para monitor")
btnMove.OnEvent("Click", MoveWindow)

btnCenter := app.AddButton("x+10 yp w110", "Centralizar")
btnCenter.OnEvent("Click", CenterWindow)

app.AddText("xm y+15", "Ajuste fino (10 pixels por clique):")

btnUp := app.AddButton("xm+170 w80", "↑")
btnLeft := app.AddButton("xm+85 y+5 w80", "←")
btnDown := app.AddButton("x+5 yp w80", "↓")
btnRight := app.AddButton("x+5 yp w80", "→")

btnUp.OnEvent("Click", (*) => Nudge(0, -10))
btnDown.OnEvent("Click", (*) => Nudge(0, 10))
btnLeft.OnEvent("Click", (*) => Nudge(-10, 0))
btnRight.OnEvent("Click", (*) => Nudge(10, 0))

app.AddText("xm y+12", "Posição atual:")

global positionText := app.AddText("w400", "Selecione uma janela.")

RefreshMonitors()
RefreshWindows()
app.Show()

RefreshMonitors() {
    global monitorData, monitorDrop

    monitorData := []
    names := []

    Loop MonitorGetCount() {
        MonitorGet(A_Index, &l, &t, &r, &b)

        monitorData.Push({X:l, Y:t})
        names.Push("Monitor " A_Index " (" (r-l) "x" (b-t) ")")
    }

    monitorDrop.Delete()
    monitorDrop.Add(names)
    monitorDrop.Choose(1)
}

RefreshWindows(*) {
    global found, lv

    found := Map()
    lv.Delete()

    callback := CallbackCreate(EnumCallback, "Fast", 2)
    DllCall("user32\EnumWindows", "Ptr", callback, "Ptr", 0)
    CallbackFree(callback)

    for hwnd, info in found
        lv.Add("", info.Title, hwnd)

    lv.ModifyCol(1, 490)
    lv.ModifyCol(2, 130)
}

EnumCallback(hwnd, lParam) {
    global found

    try {
        title := WinGetTitle("ahk_id " hwnd)
        classe := WinGetClass("ahk_id " hwnd)

        if (classe = "CHAYA::CCfFormRuntimeFrame"
            && InStr(title, "Checklifting")) {
            found[hwnd] := {Title:title}
        }
    }

    return true
}

GetSelectedWindow() {
    global lv

    row := lv.GetNext()

    if !row {
        MsgBox("Selecione uma janela primeiro.")
        return 0
    }

    return Integer(lv.GetText(row, 2))
}

MoveWindow(*) {
    global monitorDrop, monitorData

    hwnd := GetSelectedWindow()
    if !hwnd
        return

    monitor := monitorDrop.Value
    if !monitor
        return

    MoveTo(hwnd, monitorData[monitor].X, monitorData[monitor].Y)
}

Nudge(dx, dy) {
    hwnd := GetSelectedWindow()
    if !hwnd
        return

    try {
        WinGetPos(&x, &y, &w, &h, "ahk_id " hwnd)
        MoveTo(hwnd, x + dx, y + dy)
    }
}

MoveTo(hwnd, x, y) {
    global positionText

    try {
        WinGetPos(&oldX, &oldY, &w, &h, "ahk_id " hwnd)

        result := DllCall(
            "user32\SetWindowPos",
            "Ptr", hwnd,
            "Ptr", 0,
            "Int", x,
            "Int", y,
            "Int", w,
            "Int", h,
            "UInt", 0x0004,
            "Int"
        )

        if result
            positionText.Text := "X: " x " | Y: " y
        else
            MsgBox("O Windows recusou o movimento.")
    }
    catch {
        MsgBox("Não foi possível mover esta janela.")
    }
}

CenterWindow(*) {
    global monitorDrop

    hwnd := GetSelectedWindow()
    if !hwnd
        return

    monitor := monitorDrop.Value
    if !monitor
        return

    MonitorGet(monitor, &left, &top, &right, &bottom)

    try {
        WinGetPos(&oldX, &oldY, &w, &h, "ahk_id " hwnd)

        x := left + Floor(((right - left) - w) / 2)
        y := top + Floor(((bottom - top) - h) / 2)

        MoveTo(hwnd, x, y)
    }
}