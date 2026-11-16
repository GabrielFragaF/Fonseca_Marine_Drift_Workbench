"""Present validation issues and navigate using stable field identifiers."""
from collections import defaultdict

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea, QStyle, QWidget

class ValidationFeedbackMixin:
    _STEP_KEYS = ("stranding_data", "environmental_forcing", "simulation_setup", "review_run")
    _STEP_NAMES = ("01  Stranding data", "02  Environmental forcing", "03  Simulation setup", "04  Review & run", "05  Results & export")

    def _validation_field(self, field_id):
        if field_id.startswith("environment_reader:"):
            return self.environment_catalog_view
        if field_id == "catalog_table":
            return self.environment_catalog_view
        for owner in (self, self.observation_page, self.simulation_setup_page, self.review_run_page, self.environment_page):
            widget = getattr(owner, field_id, None)
            if isinstance(widget, QWidget):
                return widget
        return None

    def _clear_validation_feedback(self):
        if not hasattr(self, "_validation_original_icons"):
            self._validation_original_icons = [self.stage_navigation.item(i).icon() for i in range(5)]
        for widget, tooltip in getattr(self, "_validation_widgets", {}).items():
            widget.setProperty("validationState", "")
            widget.setToolTip(tooltip)
            self._refresh_style(widget)
        self._validation_widgets = {}
        for label in getattr(self, "_validation_banners", {}).values():
            label.hide()
        for index, text in enumerate(self._STEP_NAMES):
            item = self.stage_navigation.item(index)
            item.setText(text)
            item.setIcon(self._validation_original_icons[index])
            item.setForeground(QBrush())
            item.setToolTip("")
        self.simulation_setup_page.validation_step_issues = {}
        self.simulation_setup_page._refresh_step_ui()

    def _apply_validation_feedback(self, checks):
        self._clear_validation_feedback()
        issues_by_stage = defaultdict(list)
        issues_by_section = defaultdict(list)
        self._validation_banners = getattr(self, "_validation_banners", {})
        for issue in checks:
            if issue.level not in {"error", "warning"}:
                continue
            step = issue.target_step or "review_run"
            issues_by_stage[step].append(issue)
            if step == "simulation_setup" and issue.subsection is not None:
                issues_by_section[issue.subsection].append(issue)
            for field_id in issue.field_ids:
                widget = self._validation_field(field_id)
                if widget is None:
                    continue
                if widget not in self._validation_widgets:
                    self._validation_widgets[widget] = widget.toolTip()
                    widget.setToolTip("")
                if widget.property("validationState") != "error":
                    widget.setProperty("validationState", issue.level)
                widget.setToolTip(widget.toolTip() + ("\n" if widget.toolTip() else "") + issue.detail)
                self._refresh_style(widget)
        for step, issues in issues_by_stage.items():
            index = self._STEP_KEYS.index(step)
            errors = sum(issue.blocks_run for issue in issues)
            severity = "error" if errors else "warning"
            item = self.stage_navigation.item(index)
            item.setText(self._STEP_NAMES[index] + f"\n{'! ' + str(errors) + ' errors' if errors else '! Review warnings'}")
            item.setForeground(QColor("#ffb9b9" if errors else "#f5d18a"))
            item.setIcon(QApplication.style().standardIcon(QStyle.SP_MessageBoxCritical if errors else QStyle.SP_MessageBoxWarning))
            item.setToolTip("\n".join(issue.detail for issue in issues))
            page = self.stage_stack.widget(index)
            banner = self._validation_banners.get(step)
            if banner is None:
                banner = QLabel()
                banner.setWordWrap(True)
                banner.setTextFormat(Qt.PlainText)
                banner.setTextInteractionFlags(Qt.TextSelectableByMouse)
                banner.setObjectName("ValidationIssueBanner")
                page.content_layout.insertWidget(1, banner)
                self._validation_banners[step] = banner
            banner.setProperty("validationState", severity)
            banner.setText("\n".join(("Error: " if issue.blocks_run else "Warning: ") + issue.detail for issue in issues))
            banner.show()
            self._refresh_style(banner)
        self.simulation_setup_page.validation_step_issues = dict(issues_by_section)
        self.simulation_setup_page._refresh_step_ui()

    def _show_validation_issues(self):
        self.show_workbench()
        self.stage_navigation.setCurrentRow(3)
        QTimer.singleShot(0, lambda: self.review_run_page.ensureWidgetVisible(self.review_run_page.readiness_card, 12, 12))

    def _go_to_validation_issue(self, issue):
        self.show_workbench()
        index = self._STEP_KEYS.index(issue.target_step or "review_run")
        self.stage_navigation.setCurrentRow(index)
        if index == 2 and issue.subsection is not None:
            self.simulation_setup_page.set_current_step(issue.subsection)
            self.simulation_setup_page.step_feedback.setText(issue.detail)
            self.simulation_setup_page.step_feedback.setProperty("level", issue.level)
            self.simulation_setup_page.step_feedback.show()
            self._refresh_style(self.simulation_setup_page.step_feedback)
        widget = next((self._validation_field(key) for key in issue.field_ids if self._validation_field(key) is not None), None)
        if issue.field_ids and issue.field_ids[0].startswith("environment_reader:"):
            reader_index = int(issue.field_ids[0].split(":")[1])
            configs = self.request.data_sources.environment_readers
            if reader_index < len(configs):
                path = configs[reader_index].path
                for row in range(self.environment_catalog_model.rowCount()):
                    if self.environment_catalog_model.entry_at(row).path == path:
                        self.environment_catalog_view.selectRow(row)
                        self.environment_catalog_view.scrollTo(self.environment_catalog_model.index(row, 0))
                        break
        def reveal():
            if widget is None:
                self.stage_stack.widget(index).verticalScrollBar().setValue(0)
                return
            parent = widget.parentWidget()
            while parent is not None:
                if isinstance(parent, QScrollArea):
                    parent.ensureWidgetVisible(widget, 16, 32)
                parent = parent.parentWidget()
            widget.setFocus(Qt.OtherFocusReason)
        # Wait for the page transition and its responsive layouts to settle.
        QTimer.singleShot(180, reveal)

    def _invalidate_validation_feedback(self):
        if not getattr(self, "_validation_widgets", {}) and not getattr(self, "_validation_banners", {}):
            return
        for widget in self._validation_widgets:
            widget.setProperty("validationState", "pending")
            widget.setToolTip("Configuration changed. Validate again to check this field.")
            self._refresh_style(widget)
        for banner in self._validation_banners.values():
            if not banner.isHidden():
                banner.setProperty("validationState", "pending")
                banner.setText("Configuration changed. Validate again to refresh the errors and workload.")
                self._refresh_style(banner)
        for index, text in enumerate(self._STEP_NAMES):
            item = self.stage_navigation.item(index)
            if "\n" in item.text():
                item.setText(text + "\nNeeds revalidation")
                item.setForeground(QColor("#f5d18a"))
        page = self.simulation_setup_page
        for index in getattr(page, "validation_step_issues", {}):
            page.step_states[index] = "incomplete"
        page.validation_step_issues = {}
        page._refresh_step_ui()
