from pathlib import Path

APP_FONT_CANDIDATES = ("Source Sans 3", "Aptos", "Segoe UI", "Segoe UI Variable")


def build_stylesheet(font_family: str = APP_FONT_CANDIDATES[0]) -> str:
    return """
    QWidget {
        background: transparent;
        color: #102733;
        font-family: '__APP_FONT__';
        font-size: 14px;
    }

    QMainWindow {
        background: #f3f7f8;
    }

    #WelcomePage {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #f7fbfc, stop:0.65 #eef6f7, stop:1 #e1f0ef);
    }
    #WelcomeDescription { font-size: 20px; color: #2d5166; padding: 4px 0; }
    #WelcomeDivider { background: #ccdee4; }
    #WelcomeActionEyebrow { font-size: 11px; font-weight: 700;
        letter-spacing: 3px; color: #397385; }
    #WelcomeReferenceTitle { font-size: 17px; font-weight: 700; color: #123654; }
    #WelcomeReferenceCard { background: rgba(255,255,255,0.68); border: 1px solid #bdd9e3;
        border-radius: 14px; }
    #WelcomeActions { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #102d46, stop:1 #174d61); border-radius: 20px; }
    #WelcomeActions QLabel { color: #d4e8ef; font-size: 15px; }
    #WelcomeActions #WelcomeActionEyebrow { color: #b9dce6; }
    #WelcomeActions #WelcomeActionTitle { color: #ffffff; font-size: 29px; font-weight: 600; }
    #WelcomeActions QPushButton[variant="ghost"] {
        color: #edf8fa; background: transparent; border: 1px solid #547787; }
    #WelcomeActions QPushButton[variant="ghost"]:hover,
    #WelcomeActions QPushButton[variant="ghost"]:focus { background: #24576b; border-color: #8acfc6; }
    #WelcomePartners { background: #ffffff; border: 1px solid #d3e3e8; border-radius: 14px; }
    QToolButton#PartnerLogo { background: #ffffff; color: #0f2a44;
        border: 2px solid transparent; border-radius: 10px; padding: 6px; }
    QToolButton#PartnerLogo:hover, QToolButton#PartnerLogo:focus {
        background: #e1f2f1; border: 2px solid #078da3; }
      #TourCard { background: #ffffff; border: 2px solid #40b5ae; border-radius: 14px; }
      #TourTitle, #ValidationTitle { font-size: 22px; font-weight: 600; color: #0b4055; }
      #TourProgress { background: #dbe9eb; border: none; border-radius: 3px; }
      #TourProgress::chunk { background: #18a8a3; border-radius: 3px; }
    #ValidationPanel { background: #e1f3f2; border: 1px solid #87cfc8; border-radius: 14px; }
    #ValidationDialog { background: #e1f3f2; border: 2px solid #41aaa6; border-radius: 16px; }
    #ValidationPanel QProgressBar { background: #c5e3e4; border: none; border-radius: 5px; }
    #ValidationDialog QProgressBar { background: #c5e3e4; border: none; border-radius: 5px; }
    #ValidationPanel QProgressBar::chunk {
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #078da3,stop:1 #5bc6af);
        border-radius: 5px;
    }

    #RootFrame {
        background: #f3f7f8;
    }

    #StatusHeader, #StageRail, #StagePage {
        background: rgba(252, 252, 252, 0.92);
        border: 1px solid rgba(0, 0, 0, 0.10);
        border-radius: 16px;
    }

    #WorkflowFooter {
        background: rgba(255, 255, 255, 0.94);
        border: 1px solid rgba(11, 46, 67, 0.12);
        border-radius: 14px;
    }

    #StatusHeader {
        background: #ffffff;
        border: 1px solid #dce7eb;
        border-radius: 10px;
    }

    #StageRail {
        background: #0f2a44;
        border-color: #0f2a44;
        border-radius: 10px;
    }

    #HeaderActions {
        background: transparent;
    }

    #BrandLogo {
        background: transparent;
        border-radius: 12px;
    }

    #HeaderTitle {
        color: #0f2a44;
        font-size: 18px;
        font-weight: 600;
    }

    #HeaderSubtitle {
        color: #607681;
        font-size: 12px;
    }

    #HeaderProject {
        background: #ffffff;
        border: 1px solid transparent;
        border-left: 1px solid #dce7eb;
        padding-left: 20px;
        margin-left: 12px;
        font-size: 13px;
        color: #415d70;
    }

    #HeaderProject:hover { background: #f5f9fa; border-color: #cddfe5; }
    #HeaderProject:focus { background: #ffffff; border: 1px solid #07889b; }

    QPushButton[role="pill-value"] {
        background: transparent;
        color: #31566b;
        border: 1px solid transparent;
        padding: 2px 6px;
        font-size: 13px;
        font-weight: 600;
    }
    QPushButton[role="pill-value"]:hover { background: #dceef1; border-color: #94bdc7; }
    QPushButton[role="pill-value"]:focus { border-color: #07889b; }

    #StageCopy {
        color: #526b79;
        font-size: 14px;
    }

    #StageHero {
        background: transparent;
        border: none;
        border-radius: 0;
    }

    #StageHeroIcon {
        background: #e5f2f3;
        border: 1px solid #c8e3e5;
        border-radius: 12px;
    }

    QLabel[role="hero-kicker"] {
        color: #08778b;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.13em;
    }

    QLabel[role="caption"] {
        color: #69d4d0;
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.12em;
    }

    #StatusPill {
        background: #f2f7f9;
        border: 1px solid #dce7eb;
        border-radius: 8px;
    }

    QLabel[role="pill-label"] {
        color: #b9ccd7;
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }

    QLabel[role="pill-value"] {
        color: #31566b;
        font-size: 13px;
        font-weight: 600;
    }

    #WorkbenchSplitter {
        background: transparent;
    }

    QSplitter::handle {
        background: transparent;
        margin: 8px 5px;
        border-radius: 2px;
    }

    #RailTitle {
        color: #ffffff;
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 1px;
        padding: 0 10px 8px 10px;
    }

    QLabel[role="rail-copy"], #RailFooter {
        color: #b9ccd7;
        font-size: 12px;
    }

    #RailFooter {
        border-top: 1px solid rgba(255, 255, 255, 0.13);
        padding-top: 10px;
    }

    #StageList {
        background: transparent;
        border: none;
        color: #c2d4df;
        outline: none;
        font-size: 13px;
    }

    #StageList::item {
        border-left: 4px solid transparent;
        border-radius: 8px;
        padding: 14px 8px;
        margin: 5px 0;
    }

    #StageList::item:hover:!selected {
        background: rgba(255, 255, 255, 0.10);
        color: #e4f4f7;
    }

    #StageList::item:selected {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 rgba(95, 200, 181, 0.28), stop:0.85 rgba(95, 200, 181, 0.06), stop:1 transparent);
        border-left: 4px solid #5fc8b5;
        color: #ffffff;
        font-weight: 700;
    }

    #StageScroll, #StageScroll > QWidget, QScrollArea {
        background: transparent;
        border: none;
    }

    #StageTitle {
        color: #0b2e43;
        font-size: 25px;
        font-weight: 600;
    }

    QGroupBox {
        background: rgba(255, 255, 255, 0.97);
        border: 1px solid rgba(11, 46, 67, 0.13);
        border-radius: 12px;
        margin-top: 0;
        padding: 34px 14px 14px 14px;
        color: #102733;
    }

    QGroupBox::title {
        subcontrol-origin: padding;
        subcontrol-position: top left;
        left: 16px;
        top: 12px;
        padding: 0;
        background: transparent;
        font-weight: 600;
    }

    QGroupBox#DestinationFields {
        background: transparent;
        border: none;
        padding: 0;
        margin: 0;
    }

    QLabel {
        background: transparent;
    }

    QLabel[role="checkline"] {
        color: #0b2e43;
        border-left: 3px solid #159ab5;
        padding: 4px 0 4px 9px;
    }

    QLabel[role="dataset-title"] {
        color: #102733;
        font-weight: 800;
        padding-top: 6px;
        border-top: 1px solid rgba(0, 0, 0, 0.08);
    }

    QLabel[role="field-hint"] {
        color: #607681;
        font-size: 12px;
    }

    QLabel[role="section-kicker"] {
        color: #159ab5;
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0.10em;
        padding: 6px 2px 0 2px;
    }

    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {
        background: #ffffff;
        border: 1px solid rgba(0, 0, 0, 0.12);
        border-radius: 9px;
        padding: 8px 10px;
        min-height: 20px;
        selection-background-color: #159ab5;
        selection-color: #ffffff;
    }

    QTextEdit#LogOutput {
        background: #1a1c21;
        color: #e8eaed;
        border: 1px solid rgba(255, 255, 255, 0.12);
        font-family: 'Cascadia Mono', 'Consolas', monospace;
        font-size: 12px;
    }

    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus {
        border: 1.5px solid #07889b;
        background: #eef8f9;
    }

    QComboBox::drop-down {
        border: none;
        width: 34px;
    }

    QSpinBox, QDoubleSpinBox { padding-right: 30px; }
    QSpinBox::up-button, QDoubleSpinBox::up-button {
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: 27px;
        height: 19px;
        background: #f0f6f8;
        border-left: 1px solid #dce7eb;
        border-top-right-radius: 8px;
    }
    QSpinBox::down-button, QDoubleSpinBox::down-button {
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: 27px;
        height: 19px;
        background: #f0f6f8;
        border-left: 1px solid #dce7eb;
        border-bottom-right-radius: 8px;
    }
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
        background: #dceff1;
    }
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
        image: url('__CONTROL_ASSETS__/chevron-up.svg');
        width: 12px; height: 12px;
    }
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
        image: url('__CONTROL_ASSETS__/chevron-down.svg');
        width: 12px; height: 12px;
    }
    QComboBox { padding-right: 34px; }
    QComboBox[animated-selector="true"]::down-arrow { image: none; }
    QComboBox QAbstractItemView {
        background: #ffffff;
        color: #173b4d;
        border: 1px solid #c8dde4;
        border-radius: 8px;
        padding: 6px;
        selection-background-color: #def1f3;
        selection-color: #09576c;
        outline: none;
    }
    QComboBox QAbstractItemView::item { min-height: 32px; padding: 4px 10px; }
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {
        border-color: #86b6c3;
    }
    QPushButton:focus, QToolButton:focus { border: 1px solid #159ab5; }

    QPushButton {
        background: #ffffff;
        color: #102733;
        border: 1px solid rgba(0, 0, 0, 0.10);
        border-radius: 9px;
        padding: 9px 14px;
        font-weight: 600;
    }

    QPushButton:hover {
        background: #eaf5f6;
    }

    QPushButton:pressed {
        background: #dce4ed;
    }

    QPushButton[variant="primary"] {
        background: #07889b;
        color: #ffffff;
        border: 1px solid #087f9b;
    }

    QPushButton[variant="primary"]:hover {
        background: #087e91;
        border-color: #087e91;
    }

    QPushButton[variant="primary"]:pressed {
        background: #075f73;
        border-color: #075f73;
    }

    QPushButton[variant="primary"]:focus {
        border-color: #064356;
    }

    QPushButton[variant="secondary"] {
        background: #ffffff;
        color: #102733;
        border: 1px solid rgba(0, 0, 0, 0.10);
    }

    QPushButton[variant="secondary"]:hover {
        background: #eaf5f6;
        border-color: #94bdc7;
    }

    QPushButton[variant="ghost"] {
        background: transparent;
        color: #356273;
        border: 1px solid rgba(11, 46, 67, 0.16);
        text-align: left;
    }

    QPushButton[variant="ghost"]:hover,
    QPushButton[variant="ghost"]:checked {
        background: rgba(103, 198, 176, 0.10);
        color: #075f73;
        border-color: #67c6b0;
    }

    QPushButton[variant="danger"] {
        background: #fff2f2;
        color: #a3262e;
        border: 1px solid rgba(197, 49, 60, 0.34);
    }

    QPushButton[variant="danger"]:hover {
        background: #fde4e5;
        border-color: #c5313c;
    }

    QPushButton:disabled {
        background: #eef2f6;
        color: #a5adb6;
        border: 1px solid rgba(0, 0, 0, 0.08);
    }

    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled,
    QDoubleSpinBox:disabled {
        background: #f0f4f6;
        color: #748894;
        border-color: #dce5e9;
    }

    #PreviewState {
        background: #eef2f6;
        border: 1px solid rgba(0, 0, 0, 0.10);
        border-radius: 10px;
        color: #102733;
        font-weight: 700;
        padding: 8px 10px;
    }

    #PreviewState[state="ready"] {
        background: #e4f8ec;
        border-color: rgba(52, 199, 89, 0.38);
        color: #188038;
    }

    #PreviewState[state="attention"] {
        background: #fff2e0;
        border-color: rgba(255, 149, 0, 0.42);
        color: #9a4f00;
    }

    QCheckBox {
        background: #f7fafb;
        border: 1px solid rgba(11, 46, 67, 0.12);
        border-radius: 9px;
        padding: 8px 10px;
        spacing: 8px;
    }

    QCheckBox:hover {
        background: #eef8f8;
        border-color: rgba(22, 141, 165, 0.38);
    }

    QCheckBox::indicator {
        width: 15px;
        height: 15px;
    }

    QCheckBox::indicator:checked {
        background: #159ab5;
        border: 2px solid #159ab5;
        border-radius: 4px;
    }

    QProgressBar {
        background: #e4edf0;
        border: none;
        border-radius: 7px;
        min-height: 20px;
        text-align: center;
        color: #0b2e43;
        font-size: 11px;
        font-weight: 700;
    }

    QProgressBar::chunk {
        background: #159ab5;
        border-radius: 7px;
    }

    #PreviewState[state="running"] {
        background: #dff4f7;
        border-color: #67c6b0;
        color: #075f73;
    }

    QTableWidget, QTableView {
        background: #ffffff;
        alternate-background-color: #f4f8fa;
        border: 1px solid rgba(11, 46, 67, 0.13);
        border-radius: 10px;
        gridline-color: #dfe8ec;
        selection-background-color: #d8f1f2;
        selection-color: #0b2e43;
    }

    QTableView::item {
        min-height: 34px;
        padding: 6px 8px;
        border-bottom: 1px solid rgba(11, 46, 67, 0.07);
    }

    QTableView::item:selected {
        background: #d8f1f2;
        color: #083d51;
        border-left: 3px solid #159ab5;
    }

    QFrame#DatasetTablePanel, QFrame#DatasetInspectorPanel {
        background: rgba(255, 255, 255, 0.74);
        border: 1px solid rgba(11, 46, 67, 0.10);
        border-radius: 12px;
    }

    QFrame#DatasetInspectorPanel QListWidget {
        background: #f8fbfc;
        border: 1px solid rgba(11, 46, 67, 0.12);
        border-radius: 9px;
        padding: 4px;
    }

    QHeaderView::section {
        background: #eaf3f5;
        color: #274c5a;
        border: none;
        border-right: 1px solid #d6e3e7;
        border-bottom: 1px solid #d6e3e7;
        padding: 8px;
        font-weight: 700;
    }

    QScrollBar:vertical {
        background: transparent;
        width: 10px;
        margin: 2px;
    }

    QScrollBar::handle:vertical {
        background: rgba(0, 0, 0, 0.22);
        border-radius: 4px;
        min-height: 30px;
    }

    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }

    QScrollBar:horizontal {
        background: transparent;
        height: 10px;
        margin: 2px;
    }

    QScrollBar::handle:horizontal {
        background: rgba(0, 0, 0, 0.22);
        border-radius: 4px;
        min-width: 30px;
    }

    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0;
    }

    #StagePage {
        background: #f7fafb;
        border-color: #e0e9ed;
        border-radius: 10px;
    }

    QFrame#DataSourceCard, QFrame#FieldMappingCard {
        background: rgba(255, 255, 255, 0.94);
        border: 1px solid rgba(11, 46, 67, 0.13);
        border-radius: 10px;
    }

    QFrame#DataSourceCard {
        border-color: #cddfe5;
    }

    QFrame#FieldMappingCard {
        border-color: #cddfe5;
    }

    QFrame#SourceMetadata {
        background: #f7fafb;
        border: none;
        border-radius: 6px;
    }

    QFrame#MappingProgressSummary {
        background: transparent;
        border: none;
    }

    QFrame#MappingProgressSummary[state="valid"] {
        background: #e8f6ef;
        border-color: rgba(45, 155, 111, 0.34);
    }

    QLabel#MappingProgressLabel {
        color: #274c5a;
        font-size: 11px;
        font-weight: 700;
    }

    QProgressBar#MappingProgress {
        background: #d6e5e8;
        border: none;
        border-radius: 4px;
        min-height: 0;
        max-height: 8px;
    }

    QProgressBar#MappingProgress::chunk {
        background: #07889b;
        border-radius: 4px;
    }

    QLabel[role="metadata-label"] {
        color: #6b818b;
        font-size: 10.5px;
        font-weight: 600;
        letter-spacing: 0.7px;
    }

    QLabel[role="metadata-value"] {
        color: #173b4b;
        font-weight: 600;
    }

    QLabel[role="field-label"] {
        color: #274c5a;
        font-weight: 650;
    }

    QLabel[role="field-label"][required="true"] {
        color: #173b4b;
    }

    QFrame[role="mapping-group"] {
        background: #fbfdfe;
        border: 1px solid #e2ebef;
        border-radius: 8px;
    }

    QFrame[role="mapping-group"][state="valid"] {
        border-color: rgba(45, 155, 111, 0.42);
        background: #f5fbf8;
    }

    QFrame[role="mapping-group"][state="error"] {
        border-color: rgba(201, 95, 95, 0.45);
        background: #fff8f8;
    }

    QLabel#MappingGroupState {
        color: #58727d;
        background: #edf4f5;
        border-radius: 7px;
        padding: 6px 8px;
        font-size: 10px;
        font-weight: 650;
    }

    QLabel#MappingGroupState[state="valid"] {
        color: #176242;
        background: #e4f7ec;
        border: 1px solid #94d7b2;
        border-radius: 10px;
        padding: 4px 10px;
        font-weight: 700;
    }

    QLabel#MappingGroupState[state="error"] {
        color: #8b3138;
        background: #fdebec;
    }

    QGroupBox#InputDropzone {
        background: #f5fbfb;
        border: 1px dashed rgba(21, 154, 181, 0.48);
    }

    QGroupBox#ReaderCatalog {
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 1,
            stop: 0 #ffffff, stop: 1 #eef8f7
        );
    }

    QGroupBox#RunOverview {
        border-left: 4px solid #67c6b0;
    }

    QGroupBox#RunActions {
        background: #eef8f7;
        border-color: rgba(45, 155, 111, 0.30);
    }

    QLabel#ForcingCheck {
        background: #f7fafb;
        color: #385868;
        border: 1px solid rgba(11, 46, 67, 0.11);
        border-radius: 9px;
        padding: 9px 11px;
    }

    QLabel#ForcingCheck[level="success"] {
        background: #e8f6ef;
        color: #176242;
        border-color: rgba(45, 155, 111, 0.34);
    }

    QLabel#ForcingCheck[level="warning"] {
        background: #fff5df;
        color: #7b5515;
        border-color: rgba(219, 165, 72, 0.45);
    }

    QLabel#ForcingCheck[level="error"] {
        background: #fdebec;
        color: #8b3138;
        border-color: rgba(201, 95, 95, 0.42);
    }

    QLabel#ForcingCheck[level="info"] {
        background: #eaf4f8;
        color: #1f5f78;
        border-color: rgba(21, 154, 181, 0.28);
    }

    QFrame#ModelBuilder {
        background: transparent;
    }

    QFrame#SetupProgress, QFrame#SetupConfiguration, QFrame#SetupSummary {
        background: rgba(255, 255, 255, 0.90);
        border: 1px solid rgba(11, 46, 67, 0.12);
        border-radius: 14px;
        padding: 10px;
    }

    QFrame#SetupConfiguration {
        background: rgba(249, 252, 252, 0.96);
        border-color: rgba(21, 154, 181, 0.24);
    }

    QListWidget#InternalStepList {
        background: transparent;
        border: none;
        outline: none;
    }

    QListWidget#InternalStepList::item {
        color: #385868;
        border-left: 3px solid #c7d8dd;
        border-radius: 8px;
        padding: 10px 8px;
        margin: 2px 0;
    }

    QListWidget#InternalStepList::item:selected {
        background: #e0f4f3;
        color: #075f63;
        border-left-color: #159ab5;
        font-weight: 700;
    }

    QLabel#SetupSummaryItem {
        background: #f7fafb;
        color: #385868;
        border: 1px solid rgba(11, 46, 67, 0.10);
        border-radius: 9px;
        padding: 8px 10px;
    }

    QLabel#SetupSummaryItem[state="valid"] {
        background: #e8f6ef;
        color: #176242;
        border-color: rgba(45, 155, 111, 0.34);
    }

    QLabel#SetupSummaryItem[state="warning"] {
        background: #fff5df;
        color: #7b5515;
        border-color: rgba(219, 165, 72, 0.45);
    }

    QLabel#SetupSummaryItem[state="error"] {
        background: #fdebec;
        color: #8b3138;
        border-color: rgba(201, 95, 95, 0.42);
    }

    QLabel#SetupSummaryItem[state="incomplete"] {
        background: #eaf4f8;
        color: #1f5f78;
        border-color: rgba(21, 154, 181, 0.28);
    }

    QLabel#SetupStepFeedback {
        border-radius: 9px;
        padding: 9px 11px;
    }

    QLabel#SetupStepFeedback[level="error"] {
        background: #fdebec;
        color: #8b3138;
        border: 1px solid rgba(201, 95, 95, 0.42);
    }

    QLabel#SetupStepFeedback[level="incomplete"] {
        background: #eaf4f8;
        color: #1f5f78;
        border: 1px solid rgba(21, 154, 181, 0.28);
    }

    QGroupBox#RunDestinationCard, QGroupBox#ReadinessCard,
    QGroupBox#RunSummaryCard, QGroupBox#ExecutionOptionsCard,
    QGroupBox#RunActivityCard {
        background: rgba(255, 255, 255, 0.94);
        border: 1px solid rgba(11, 46, 67, 0.13);
        border-radius: 14px;
        padding-top: 34px;
    }

    QGroupBox#ResultsSourceCard, QGroupBox#ResultsSamplingCard,
    QGroupBox#ResultsFormatsCard, QGroupBox#ResultsActivityCard {
        background: rgba(255, 255, 255, 0.96);
        border: 1px solid rgba(11, 46, 67, 0.14);
        border-radius: 14px;
        padding-top: 34px;
    }

    #ResultsStatusTitle {
        color: #0b2e43;
        font-size: 17px;
        font-weight: 800;
    }

    QGroupBox#ReadinessCard {
        border-color: #cddfe5;
    }

    QGroupBox#RunSummaryCard {
        border-color: #cddfe5;
    }

    QGroupBox#ExecutionOptionsCard {
        border-color: #cddfe5;
    }

    QFrame#PrimaryActionCard {
        background: qlineargradient(
            x1: 0, y1: 0, x2: 1, y2: 0,
            stop: 0 #e8f5f4, stop: 1 #f5fafb
        );
        border: 1px solid rgba(21, 154, 181, 0.25);
        border-radius: 14px;
    }

    QFrame#PrimaryActionCard[state="ready"] {
        background: #e8f6ef;
        border-color: rgba(45, 155, 111, 0.40);
    }

    QFrame#PrimaryActionCard[state="running"] {
        background: #eaf4f8;
        border-color: rgba(21, 154, 181, 0.42);
    }

    QFrame#PrimaryActionCard[state="warning"] {
        background: #fff5df;
        border-color: rgba(219, 165, 72, 0.50);
    }

    QFrame#PrimaryActionCard[state="error"] {
        background: #fdebec;
        border-color: rgba(201, 95, 95, 0.48);
    }

    QWidget#InlineValidation {
        background: transparent;
        min-width: 260px;
        max-width: 260px;
    }

    QLabel#InlineValidationLabel {
        color: #087f8f;
        font-size: 12px;
        font-weight: 700;
    }

    QProgressBar#InlineValidationProgress {
        background: #cfe6e8;
        border: none;
        border-radius: 4px;
        min-height: 9px;
        max-height: 9px;
    }

    QProgressBar#InlineValidationProgress::chunk {
        background: #12a8b8;
        border-radius: 4px;
    }

    QLabel#PrimaryStateTitle {
        color: #0b2e43;
        font-size: 16px;
        font-weight: 800;
    }

    QFrame#RunSummaryValue {
        background: transparent;
        border-bottom: 1px solid rgba(11, 46, 67, 0.08);
    }

    QLabel[role="eyebrow"] {
        color: #527180;
        font-size: 10px;
        font-weight: 800;
    }

    QLabel[role="muted"] {
        color: #527180;
    }

    QLabel#ValidationIssueBanner {
        padding: 12px;
        border-radius: 8px;
        font-weight: 600;
    }

    QWidget[validationState="error"] {
        border: 2px solid #c83d49;
        background-color: #fff2f3;
        color: #852330;
    }

    QWidget[validationState="warning"], QWidget[validationState="pending"] {
        border: 1px solid #c79535;
        background-color: #fff7e7;
        color: #715015;
    }

    QFrame#ReadinessRow {
        background: #f7fafb;
        border: 1px solid rgba(11, 46, 67, 0.10);
        border-radius: 9px;
    }

    QFrame#ReadinessRow[severity="success"] {
        background: #e8f6ef;
        border-color: rgba(45, 155, 111, 0.34);
    }

    QFrame#ReadinessRow[severity="warning"] {
        background: #fff5df;
        border-color: rgba(219, 165, 72, 0.45);
    }

    QFrame#ReadinessRow[severity="error"] {
        background: #fdebec;
        border-color: rgba(201, 95, 95, 0.42);
    }

    QLabel[role="readiness-title"] {
        color: #173c4d;
        font-weight: 800;
    }

    QTabWidget::pane {
        background: #f8fbfc;
        border: 1px solid rgba(11, 46, 67, 0.12);
        border-radius: 10px;
    }

    QTabBar::tab {
        background: #e6eef1;
        color: #385868;
        border: 1px solid rgba(11, 46, 67, 0.10);
        padding: 8px 16px;
    }

    QTabBar::tab:selected {
        background: #ffffff;
        color: #075f63;
        border-bottom-color: #ffffff;
        font-weight: 800;
    }

    QToolButton[role="selection-tile"] {
        background: #f8fbfc;
        color: #274c5a;
        border: 1px solid rgba(11, 46, 67, 0.14);
        border-radius: 10px;
        min-height: 34px;
        padding: 8px 12px;
        text-align: left;
        font-weight: 700;
    }

    QToolButton[role="selection-tile"]:hover {
        background: #edf8f8;
        border-color: rgba(21, 154, 181, 0.55);
    }

    QToolButton[role="selection-tile"]:checked {
        background: #dff4ef;
        color: #075f63;
        border: 1px solid #309f91;
    }

    QAbstractButton[role="animated-toggle"]:checked {
        color: #102733;
    }

    QMessageBox { background: #f6fafb; color: #102f43; }
    QMessageBox QLabel { background: transparent; color: #102f43; }
    QMessageBox QTextEdit { background: #ffffff; color: #102f43; }
    QMessageBox QPushButton { background: #ffffff; color: #102f43; border: 1px solid #a8c4cc; }
    QMessageBox QPushButton:hover { background: #e2f2f3; }

    QToolTip {
        background: #071a26;
        color: #ffffff;
        border: 1px solid #155a72;
        border-radius: 6px;
        padding: 6px 8px;
    }

    #WorkflowFooter ActionButton[variant="primary"] {
        min-width: 112px;
    }
    """.replace("__APP_FONT__", font_family).replace(
        "__CONTROL_ASSETS__", (Path(__file__).parent / "assets" / "controls").as_posix()
    )
