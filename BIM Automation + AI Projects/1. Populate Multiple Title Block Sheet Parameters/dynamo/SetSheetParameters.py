import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

import System
from System.Windows import Window, Thickness, HorizontalAlignment, VerticalAlignment, GridLength, GridUnitType, TextDecorations
from System.Windows.Controls import Button, StackPanel, Grid, TextBox, TextBlock, ScrollViewer, ColumnDefinition
from System.Windows.Documents import Run, Underline
from System.Windows.Media import SolidColorBrush, Color

# Revit API & Dynamo Imports
clr.AddReference('RevitServices')
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import StorageType, ElementId

doc = DocumentManager.Instance.CurrentDBDocument

raw_input = IN[0]

def set_param_value(param, val_str):
    st = param.StorageType
    if st == StorageType.String:
        return param.Set(str(val_str))
    elif st == StorageType.Integer:
        v_clean = str(val_str).strip().lower()
        if v_clean in ['true', 'yes', '1']:
            return param.Set(1)
        elif v_clean in ['false', 'no', '0']:
            return param.Set(0)
        return param.Set(int(v_clean))
    elif st == StorageType.Double:
        return param.Set(float(val_str))
    elif st == StorageType.ElementId:
        return param.Set(ElementId(int(val_str)))
    return False

OUT = []

try:
    if raw_input is None:
        OUT = "Error: Input IN[0] is None."
    else:
        wrapped_sheets = raw_input if isinstance(raw_input, list) else [raw_input]
        wrapped_sheets = [s for s in wrapped_sheets if s is not None]

        if len(wrapped_sheets) == 0:
            OUT = "Error: Input list IN[0] contains no valid sheets."
        else:
            db_sheets = []
            for s in wrapped_sheets:
                if hasattr(s, "InternalElement"):
                    db_sheets.append(s.InternalElement)
                else:
                    db_sheets.append(s)

            # -------------------------------------------------------------
            # MAIN INPUT UI
            # -------------------------------------------------------------
            win = Window()
            win.Title = "Set Parameters for Selected Sheets"
            win.Width = 560
            win.Height = 450
            win.WindowStartupLocation = System.Windows.WindowStartupLocation.CenterScreen

            main_stack = StackPanel()
            main_stack.Margin = Thickness(15)

            header = TextBlock()
            header.Text = f"Targeting {len(db_sheets)} Sheet(s)"
            header.FontSize = 14
            header.FontWeight = System.Windows.FontWeights.Bold
            header.Margin = Thickness(0, 0, 0, 10)
            main_stack.Children.Add(header)

            rows_panel = StackPanel()
            param_row_controls = []

            def add_parameter_row(default_name="", default_val=""):
                grid = Grid()
                grid.Margin = Thickness(0, 0, 0, 8)

                col1 = ColumnDefinition()
                col1.Width = GridLength(1.0, GridUnitType.Star)
                col2 = ColumnDefinition()
                col2.Width = GridLength(1.0, GridUnitType.Star)
                col3 = ColumnDefinition()
                col3.Width = GridLength(40, GridUnitType.Pixel)

                grid.ColumnDefinitions.Add(col1)
                grid.ColumnDefinitions.Add(col2)
                grid.ColumnDefinitions.Add(col3)

                tb_name = TextBox()
                tb_name.Text = default_name
                tb_name.Margin = Thickness(0, 0, 5, 0)
                tb_name.Height = 26
                tb_name.VerticalContentAlignment = VerticalAlignment.Center
                Grid.SetColumn(tb_name, 0)

                tb_val = TextBox()
                tb_val.Text = default_val
                tb_val.Margin = Thickness(5, 0, 5, 0)
                tb_val.Height = 26
                tb_val.VerticalContentAlignment = VerticalAlignment.Center
                Grid.SetColumn(tb_val, 1)

                btn_del = Button()
                btn_del.Content = "✕"
                btn_del.Height = 26
                btn_del.Margin = Thickness(5, 0, 0, 0)
                btn_del.Background = SolidColorBrush(Color.FromRgb(240, 128, 128))
                Grid.SetColumn(btn_del, 2)

                def remove_row(sender, e):
                    rows_panel.Children.Remove(grid)
                    if (tb_name, tb_val) in param_row_controls:
                        param_row_controls.remove((tb_name, tb_val))

                btn_del.Click += remove_row

                grid.Children.Add(tb_name)
                grid.Children.Add(tb_val)
                grid.Children.Add(btn_del)

                rows_panel.Children.Add(grid)
                param_row_controls.append((tb_name, tb_val))

            header_grid = Grid()
            header_grid.Margin = Thickness(0, 0, 0, 5)

            c1 = ColumnDefinition()
            c1.Width = GridLength(1.0, GridUnitType.Star)
            c2 = ColumnDefinition()
            c2.Width = GridLength(1.0, GridUnitType.Star)
            c3 = ColumnDefinition()
            c3.Width = GridLength(40, GridUnitType.Pixel)

            header_grid.ColumnDefinitions.Add(c1)
            header_grid.ColumnDefinitions.Add(c2)
            header_grid.ColumnDefinitions.Add(c3)

            lbl1 = TextBlock()
            lbl1.Text = "Parameter Name"
            lbl1.FontWeight = System.Windows.FontWeights.SemiBold
            Grid.SetColumn(lbl1, 0)

            lbl2 = TextBlock()
            lbl2.Text = "Value to Set"
            lbl2.FontWeight = System.Windows.FontWeights.SemiBold
            Grid.SetColumn(lbl2, 1)

            header_grid.Children.Add(lbl1)
            header_grid.Children.Add(lbl2)
            main_stack.Children.Add(header_grid)

            scroll_view = ScrollViewer()
            scroll_view.Height = 260
            scroll_view.Content = rows_panel
            main_stack.Children.Add(scroll_view)

            btn_panel = StackPanel()
            btn_panel.Orientation = System.Windows.Controls.Orientation.Horizontal
            btn_panel.Margin = Thickness(0, 15, 0, 0)
            btn_panel.HorizontalAlignment = HorizontalAlignment.Right

            btn_add = Button()
            btn_add.Content = "+ Add Parameter"
            btn_add.Width = 120
            btn_add.Height = 30
            btn_add.Margin = Thickness(0, 0, 10, 0)

            def on_add_click(sender, e):
                add_parameter_row()

            btn_add.Click += on_add_click
            btn_panel.Children.Add(btn_add)

            btn_apply = Button()
            btn_apply.Content = "Apply"
            btn_apply.Width = 80
            btn_apply.Height = 30
            btn_apply.Background = SolidColorBrush(Color.FromRgb(144, 238, 144))

            def on_apply_click(sender, e):
                win.DialogResult = True
                win.Close()

            btn_apply.Click += on_apply_click
            btn_panel.Children.Add(btn_apply)

            main_stack.Children.Add(btn_panel)
            win.Content = main_stack

            add_parameter_row("Drawn By", "")

            # -------------------------------------------------------------
            # EXECUTION & REPORT GENERATION
            # -------------------------------------------------------------
            if win.ShowDialog() == True:
                param_updates = []
                for tb_name, tb_val in param_row_controls:
                    p_name = tb_name.Text.strip()
                    p_val = tb_val.Text
                    if p_name:
                        param_updates.append((p_name, p_val))

                error_logs = []
                successful_sheets = set()
                successful_params = set()

                TransactionManager.Instance.EnsureInTransaction(doc)
                try:
                    for sheet in db_sheets:
                        s_num = getattr(sheet, "SheetNumber", str(sheet.Id))
                        s_name = getattr(sheet, "Name", "")
                        label = f"{s_num} - {s_name}" if s_name else s_num

                        for p_name, p_val in param_updates:
                            param = sheet.LookupParameter(p_name)

                            if param is None:
                                error_logs.append((p_name, f"Parameter '{p_name}' does not exist on sheet {label}."))
                            elif param.IsReadOnly:
                                error_logs.append((p_name, f"Parameter '{p_name}' is read-only on sheet {label}."))
                            else:
                                try:
                                    success = set_param_value(param, p_val)
                                    if success:
                                        successful_sheets.add(label)
                                        successful_params.add(p_name)
                                    else:
                                        error_logs.append((p_name, f"Failed to write value to parameter '{p_name}' on sheet {label}."))
                                except Exception as ex:
                                    error_logs.append((p_name, f"Error setting '{p_name}' on sheet {label}: {str(ex)}"))
                finally:
                    # Always close the transaction, even if something unexpected fails inside the loop
                    TransactionManager.Instance.TransactionTaskDone()

                doc.Regenerate()

                # -------------------------------------------------------------
                # REPORT DIALOG POPUP
                # -------------------------------------------------------------
                report_win = Window()
                report_win.Title = "Execution Report"
                report_win.Width = 550
                report_win.Height = 480
                report_win.WindowStartupLocation = System.Windows.WindowStartupLocation.CenterScreen

                report_stack = StackPanel()
                report_stack.Margin = Thickness(15)

                report_scroll = ScrollViewer()
                report_scroll.Height = 360

                inner_report_stack = StackPanel()

                # 1. Error Section
                if error_logs:
                    err_header = TextBlock()
                    err_header.Text = "Errors & Missing Parameters:"
                    err_header.FontSize = 13
                    err_header.FontWeight = System.Windows.FontWeights.Bold
                    err_header.Foreground = SolidColorBrush(Color.FromRgb(200, 30, 30))
                    err_header.Margin = Thickness(0, 0, 0, 5)
                    inner_report_stack.Children.Add(err_header)

                    for p_name, err in error_logs:
                        err_txt = TextBlock()
                        err_txt.Margin = Thickness(10, 0, 0, 3)
                        err_txt.TextWrapping = System.Windows.TextWrapping.Wrap

                        parts = err.split(f"'{p_name}'")
                        if len(parts) == 2:
                            err_txt.Inlines.Add(Run(f"• {parts[0]}'"))
                            p_run = Run(p_name)
                            p_run.TextDecorations = TextDecorations.Underline
                            err_txt.Inlines.Add(p_run)
                            err_txt.Inlines.Add(Run(f"'{parts[1]}"))
                        else:
                            err_txt.Inlines.Add(Run(f"• {err}"))

                        inner_report_stack.Children.Add(err_txt)

                    # Error Summary Footer at the Bottom of Error Section
                    err_summary = TextBlock()
                    err_summary.Text = f"Total Errors Encountered: {len(error_logs)}"
                    err_summary.FontWeight = System.Windows.FontWeights.Bold
                    err_summary.Foreground = SolidColorBrush(Color.FromRgb(200, 30, 30))
                    err_summary.Margin = Thickness(10, 5, 0, 0)
                    inner_report_stack.Children.Add(err_summary)

                    sep = TextBlock()
                    sep.Text = "----------------------------------------------------------------------------------"
                    sep.Margin = Thickness(0, 10, 0, 10)
                    sep.Foreground = SolidColorBrush(Color.FromRgb(180, 180, 180))
                    inner_report_stack.Children.Add(sep)

                # 2. Success Section
                succ_header = TextBlock()
                succ_header.FontSize = 13
                succ_header.FontWeight = System.Windows.FontWeights.Bold
                succ_header.Foreground = SolidColorBrush(Color.FromRgb(30, 140, 30))
                succ_header.Margin = Thickness(0, 0, 0, 5)
                succ_header.TextWrapping = System.Windows.TextWrapping.Wrap

                succ_header.Inlines.Add(Run("Successful replacement of Parameters "))

                param_list = sorted(list(successful_params))
                if not param_list:
                    succ_header.Inlines.Add(Run("N/A"))
                else:
                    for i, p_name in enumerate(param_list):
                        u_run = Run(p_name)
                        u_run.TextDecorations = TextDecorations.Underline
                        succ_header.Inlines.Add(u_run)

                        if len(param_list) == 2 and i == 0:
                            succ_header.Inlines.Add(Run(" and "))
                        elif i < len(param_list) - 2:
                            succ_header.Inlines.Add(Run(", "))
                        elif i == len(param_list) - 2:
                            succ_header.Inlines.Add(Run(", and "))

                succ_header.Inlines.Add(Run(" for sheets:"))
                inner_report_stack.Children.Add(succ_header)

                if successful_sheets:
                    for s_label in sorted(list(successful_sheets)):
                        succ_txt = TextBlock()
                        succ_txt.Text = f"• {s_label}"
                        succ_txt.Margin = Thickness(10, 0, 0, 3)
                        inner_report_stack.Children.Add(succ_txt)
                else:
                    none_txt = TextBlock()
                    none_txt.Text = "• No sheet parameters were updated."
                    none_txt.Margin = Thickness(10, 0, 0, 3)
                    inner_report_stack.Children.Add(none_txt)

                # Success Summary Footer at the Bottom of Success Section
                succ_summary = TextBlock()
                succ_summary.Text = f"Total Sheets Successfully Updated: {len(successful_sheets)}"
                succ_summary.FontWeight = System.Windows.FontWeights.Bold
                succ_summary.Foreground = SolidColorBrush(Color.FromRgb(30, 140, 30))
                succ_summary.Margin = Thickness(10, 8, 0, 0)
                inner_report_stack.Children.Add(succ_summary)

                report_scroll.Content = inner_report_stack
                report_stack.Children.Add(report_scroll)

                # Close Button
                btn_close = Button()
                btn_close.Content = "Close"
                btn_close.Width = 80
                btn_close.Height = 30
                btn_close.Margin = Thickness(0, 10, 0, 0)
                btn_close.HorizontalAlignment = HorizontalAlignment.Right

                def on_close_click(sender, e):
                    report_win.Close()

                btn_close.Click += on_close_click
                report_stack.Children.Add(btn_close)

                report_win.Content = report_stack
                report_win.ShowDialog()

                OUT = {
                    "TotalErrors": len(error_logs),
                    "TotalUpdatedSheets": len(successful_sheets),
                    "Errors": [e[1] for e in error_logs],
                    "UpdatedSheets": sorted(list(successful_sheets)),
                    "UpdatedParameters": sorted(list(successful_params))
                }
            else:
                OUT = "Operation cancelled by user."

except Exception as global_ex:
    OUT = f"Global Script Error: {str(global_ex)}"