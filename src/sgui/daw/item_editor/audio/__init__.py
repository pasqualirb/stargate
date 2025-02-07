"""

"""
from . import _shared
from .item import AudioSeqItem
from ..abstract import AbstractItemEditor
from sglib.math import clip_min, clip_value
from sgui import shared as glbl_shared
from sgui import widgets
from sgui.daw import shared
from sgui.daw.filedragdrop import FileDragDropper
from sglib.models.daw import *
from sgui.daw.shared import *
from sgui.daw.lib import item as item_lib
from sglib import constants
from sglib.lib import util
from sglib.lib import strings as sg_strings
from sglib.lib.util import *
from sglib.lib.translate import _
from sglib.log import LOG
from sgui.sgqt import *
from sglib.models import theme
from sglib.models.stargate.audio_pool import PerFileFX
from sgui.util import get_font



def papifx_val_callback(a_port, a_val):
    if _shared.CURRENT_ITEM is not None:
        constants.DAW_PROJECT.ipc().audio_per_file_fx(
            _shared.CURRENT_ITEM.audio_item.uid,
            a_port,
            a_val,
        )

def papifx_rel_callback(a_port, a_val):
    if _shared.CURRENT_ITEM is not None:
        pool = constants.PROJECT.get_audio_pool()
        controls = shared.AUDIO_SEQ_WIDGET.papifx.get_list()
        fx = PerFileFX(
            _shared.CURRENT_ITEM.audio_item.uid,
            controls,
        )
        pool.set_per_file_fx(fx)
        constants.PROJECT.save_audio_pool(pool)

def paif_val_callback(a_port, a_val):
    if (
        shared.CURRENT_ITEM is not None
        and
        _shared.CURRENT_AUDIO_ITEM_INDEX is not None
    ):
        constants.DAW_PROJECT.ipc().audio_per_item_fx(
            shared.CURRENT_ITEM.uid,
            _shared.CURRENT_AUDIO_ITEM_INDEX,
            a_port,
            a_val,
        )

def paif_rel_callback(a_port, a_val):
    if (
        shared.CURRENT_ITEM is not None
        and
        _shared.CURRENT_AUDIO_ITEM_INDEX is not None
    ):
        f_index_list = shared.AUDIO_SEQ_WIDGET.paifx.get_list()
        shared.CURRENT_ITEM.set_row(
            _shared.CURRENT_AUDIO_ITEM_INDEX,
            f_index_list,
        )
        item_lib.save_item(
            shared.CURRENT_ITEM_NAME,
            shared.CURRENT_ITEM,
        )

class AudioItemSeq(AbstractItemEditor):
    """ This is the QGraphicsView and QGraphicsScene for editing audio
        items within a SequencerItem on the "Items" tab.
    """
    def __init__(self):
        AbstractItemEditor.__init__(self)
        self.reset_line_lists()
        self.h_zoom = 1.0
        self.v_zoom = 1.0
        self.scene = QGraphicsScene(self)
        self.scene.dropEvent = self.sceneDropEvent
        self.scene.dragEnterEvent = self.sceneDragEnterEvent
        self.scene.dragMoveEvent = self.sceneDragMoveEvent
        self.scene.setBackgroundBrush(
            QColor(
                theme.SYSTEM_COLORS.widgets.default_scene_background,
            ),
        )
        self.scene.selectionChanged.connect(self.scene_selection_changed)
        self.setAcceptDrops(True)
        self.setScene(self.scene)
        self.audio_items = []
        self.track = 0
        self.gradient_index = 0
        self.playback_px = 0.0
        self.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignTop
            |
            QtCore.Qt.AlignmentFlag.AlignLeft
        )
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.is_playing = False
        self.reselect_on_stop = []
        #Somewhat slow on my AMD 5450 using the FOSS driver
        #self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.context_menu_enabled = True

    def reset_line_lists(self):
        self.text_list = []
        self.beat_line_list = []

    def prepare_to_quit(self):
        self.scene.clearSelection()
        self.scene.clear()

    def keyPressEvent(self, a_event):
        #Done this way to prevent the sequence editor from grabbing the key
        if a_event.key() == QtCore.Qt.Key.Key_Delete:
            self.delete_selected()
        else:
            QGraphicsView.keyPressEvent(self, a_event)
        QApplication.restoreOverrideCursor()

    def scrollContentsBy(self, x, y):
        QGraphicsView.scrollContentsBy(self, x, y)
        self.set_header_y_pos()

    def set_header_y_pos(self):
        f_point = self.get_scene_pos()
        self.header.setPos(0.0, f_point.y())
        self.verticalScrollBar().setMinimum(0)

    def get_scene_pos(self):
        return QtCore.QPointF(
            float(self.horizontalScrollBar().value()),
            float(self.verticalScrollBar().value()),
        )

    def get_selected(self):
        return [x for x in self.audio_items if x.isSelected()]

    def delete_selected(self):
        if self.check_running():
            return
        f_items = shared.CURRENT_ITEM
        f_paif = shared.CURRENT_ITEM
        for f_item in self.get_selected():
            f_items.remove_item(f_item.track_num)
            f_paif.clear_row_if_exists(f_item.track_num)
        item_lib.save_item(shared.CURRENT_ITEM_NAME, shared.CURRENT_ITEM)
        constants.DAW_PROJECT.commit(_("Delete audio item(s)"))
        global_open_audio_items(True)

    def crossfade_selected(self):
        f_list = self.get_selected()
        if len(f_list) < 2:
            QMessageBox.warning(
                shared.MAIN_WINDOW,
                _("Error"),
                _("You must have at least 2 items selected to crossfade"),
            )
            return

        f_tempo = shared.CURRENT_SEQUENCE.get_tempo_at_pos(
            shared.CURRENT_ITEM_REF.start_beat,
        )
        f_changed = False

        for f_item in f_list:
            f_start_sec = util.musical_time_to_seconds(
                f_tempo, f_item.audio_item.start_bar,
                f_item.audio_item.start_beat)
            f_time_frac = f_item.audio_item.sample_end - \
                f_item.audio_item.sample_start
            f_time_frac *= 0.001
            f_time = f_item.graph_object.length_in_seconds * f_time_frac
            f_end_sec = f_start_sec + f_time
            f_list2 = [x for x in f_list if x.audio_item != f_item.audio_item]

            for f_item2 in f_list2:
                f_start_sec2 = util.musical_time_to_seconds(
                    f_tempo, f_item2.audio_item.start_bar,
                    f_item2.audio_item.start_beat)
                f_time_frac2 = f_item2.audio_item.sample_end - \
                    f_item2.audio_item.sample_start
                f_time_frac2 *= 0.001
                f_time2 = f_item2.graph_object.length_in_seconds * f_time_frac2
                f_end_sec2 = f_start_sec2 + f_time2

                if (
                    f_start_sec > f_start_sec2
                    and
                    f_end_sec > f_end_sec2
                    and
                    f_end_sec2 > f_start_sec  # item1 is after item2
                ):
                    f_changed = True
                    f_diff_sec = f_end_sec2 - f_start_sec
                    f_val = (f_diff_sec / f_time) * 1000.0
                    f_item.audio_item.set_fade_in(f_val)
                elif (
                    f_start_sec < f_start_sec2
                    and
                    f_end_sec < f_end_sec2
                    and
                    f_end_sec > f_start_sec2  # item1 is before item2
                ):
                    f_changed = True
                    f_diff_sec = f_start_sec2 - f_start_sec
                    f_val = (f_diff_sec / f_time) * 1000.0
                    f_item.audio_item.set_fade_out(f_val)

        if f_changed:
            item_lib.save_item(shared.CURRENT_ITEM_NAME, shared.CURRENT_ITEM)
            constants.DAW_PROJECT.commit(_("Crossfade audio items"))
            global_open_audio_items(True)


    def set_tooltips(self, a_on):
        if a_on:
            self.setToolTip(sg_strings.AudioItemSeq)
        else:
            self.setToolTip("")
        for f_item in self.audio_items:
            f_item.set_tooltips(a_on)

    def resizeEvent(self, a_event):
        QGraphicsView.resizeEvent(self, a_event)
        set_audio_seq_zoom(self.h_zoom, self.v_zoom)
        global_open_audio_items(a_reload=False)

    def scene_selection_changed(self):
        f_selected_items = []
        for f_item in self.audio_items:
            f_item.set_brush()
            if f_item.isSelected():
                f_selected_items.append(f_item)
        if len(f_selected_items) == 1:
            _shared.CURRENT_ITEM = f_selected_items[0]
            _shared.CURRENT_AUDIO_ITEM_INDEX = f_selected_items[0].track_num
            shared.AUDIO_SEQ_WIDGET.paifx.widget.setEnabled(True)
            shared.AUDIO_SEQ_WIDGET.paifx.set_from_list(
                shared.CURRENT_ITEM.get_row(
                    _shared.CURRENT_AUDIO_ITEM_INDEX,
                ),
            )
            shared.AUDIO_SEQ_WIDGET.papifx.widget.setEnabled(True)

            pool = constants.PROJECT.get_audio_pool()
            per_file_fx_by_uid = pool.per_file_fx_by_uid()
            uid = _shared.CURRENT_ITEM.audio_item.uid
            if uid in per_file_fx_by_uid:
                fx = per_file_fx_by_uid[uid]
                shared.AUDIO_SEQ_WIDGET.papifx.set_from_list(fx.controls)
            else:
                shared.AUDIO_SEQ_WIDGET.papifx.clear_effects()
            shared.AUDIO_SEQ_WIDGET.paifx_stack.setCurrentIndex(0)
            shared.AUDIO_SEQ_WIDGET.papifx_stack.setCurrentIndex(0)
        elif len(f_selected_items) == 0:
            _shared.CURRENT_AUDIO_ITEM_INDEX = None
            _shared.CURRENT_ITEM = None
            shared.AUDIO_SEQ_WIDGET.paifx_stack.setCurrentIndex(1)
            shared.AUDIO_SEQ_WIDGET.papifx_stack.setCurrentIndex(1)
            shared.AUDIO_SEQ_WIDGET.papifx.widget.setDisabled(True)
            shared.AUDIO_SEQ_WIDGET.paifx.widget.setDisabled(True)
        else:
            _shared.CURRENT_ITEM = None
            shared.AUDIO_SEQ_WIDGET.paifx_stack.setCurrentIndex(1)
            shared.AUDIO_SEQ_WIDGET.papifx_stack.setCurrentIndex(1)
            shared.AUDIO_SEQ_WIDGET.papifx.widget.setDisabled(True)
            shared.AUDIO_SEQ_WIDGET.paifx.widget.setDisabled(True)

    def sceneDragEnterEvent(self, a_event):
        a_event.setAccepted(True)

    def sceneDragMoveEvent(self, a_event):
        a_event.setDropAction(QtCore.Qt.DropAction.CopyAction)

    def check_running(self):
        if (
            not shared.CURRENT_ITEM
            or
            glbl_shared.IS_PLAYING
        ):
            return True
        return False

    def sceneDropEvent(self, a_event):
        if not shared.ITEM_EDITOR.enabled:
            shared.ITEM_EDITOR.show_not_enabled_warning()
            return
        if shared.AUDIO_ITEMS_TO_DROP:
            f_x = a_event.scenePos().x()
            f_y = a_event.scenePos().y()
            self.add_items(f_x, f_y, shared.AUDIO_ITEMS_TO_DROP)

    def add_items(self, f_x, f_y, a_item_list):
        if self.check_running():
            return

        f_beat_frac = f_x / shared.AUDIO_PX_PER_BEAT
        f_beat_frac = clip_min(f_beat_frac, 0.0)
        LOG.info("f_beat_frac: {}".format(f_beat_frac))
        if shared.AUDIO_QUANTIZE:
            f_beat_frac = int(
                f_beat_frac * shared.AUDIO_QUANTIZE_AMT
            ) / shared.AUDIO_QUANTIZE_AMT

        f_lane_num = int(
            (f_y - shared.AUDIO_RULER_HEIGHT) / shared.AUDIO_ITEM_HEIGHT
        )
        f_lane_num = clip_value(f_lane_num, 0, shared.AUDIO_ITEM_MAX_LANE)

        f_items = shared.CURRENT_ITEM

        for f_file_name in a_item_list:
            f_file_name_str = str(f_file_name)
            if not f_file_name_str is None and not f_file_name_str == "":
                f_index = f_items.get_next_index()
                if f_index == -1:
                    QMessageBox.warning(self, _("Error"),
                    _("No more available audio item slots, "
                    "max per sequence is {}").format(MAX_AUDIO_ITEM_COUNT))
                    break
                else:
                    f_uid = constants.PROJECT.get_wav_uid_by_name(
                        f_file_name_str,
                    )
                    f_item = DawAudioItem(
                        f_uid,
                        a_start_bar=0,
                        a_start_beat=f_beat_frac,
                        a_lane_num=f_lane_num,
                    )
                    f_items.add_item(f_index, f_item)
                    f_graph = constants.PROJECT.get_sample_graph_by_uid(
                        f_uid,
                    )
                    f_audio_item = shared.AUDIO_SEQ.draw_item(
                        f_index, f_item, f_graph)
                    f_audio_item.clip_at_sequence_end()
        item_lib.save_item(shared.CURRENT_ITEM_NAME, shared.CURRENT_ITEM)
        constants.DAW_PROJECT.commit(
            _("Added audio items to item {}").format(shared.CURRENT_ITEM.uid))
        global_open_audio_items()
        self.last_open_dir = os.path.dirname(f_file_name_str)

    def reset_selection(self):
        for f_item in self.audio_items:
            if str(f_item.audio_item) in self.reselect_on_stop:
                f_item.setSelected(True)

    def set_zoom(self, a_scale):
        self.h_zoom = a_scale
        self.update_zoom()

    def set_v_zoom(self, a_scale):
        self.v_zoom = a_scale
        self.update_zoom()

    def update_zoom(self):
        set_audio_seq_zoom(self.h_zoom, self.v_zoom)

    def check_line_count(self):
        """ Check that there are not too many vertical
            lines on the screen
        """
        f_num_count = len(self.text_list)
        if f_num_count == 0:
            return
        f_num_visible_count = int(f_num_count /
            clip_min(self.h_zoom, 1))

        if f_num_visible_count > 24:
            for f_line in self.beat_line_list:
                f_line.setVisible(False)
            f_factor = f_num_visible_count // 24
            if f_factor == 1:
                for f_num in self.text_list:
                    f_num.setVisible(True)
            else:
                f_factor = int(round(f_factor / 2.0) * 2)
                for f_num in self.text_list:
                    f_num.setVisible(False)
                for f_num in self.text_list[::f_factor]:
                    f_num.setVisible(True)
        else:
            for f_line in self.beat_line_list:
                f_line.setVisible(True)
            for f_num in self.text_list:
                f_num.setVisible(True)


    def draw_header(self):
        f_sequence_length = shared.CURRENT_ITEM_LEN
        f_size = shared.AUDIO_PX_PER_BEAT * f_sequence_length
        self.total_height = (shared.AUDIO_ITEM_LANE_COUNT *
            (shared.AUDIO_ITEM_HEIGHT)) + shared.AUDIO_RULER_HEIGHT
        AbstractItemEditor.draw_header(
            self,
            f_size,
            shared.AUDIO_RULER_HEIGHT,
        )
        self.header.setZValue(1500.0)
        self.scene.addItem(self.header)
        if shared.ITEM_REF_POS:
            f_start, f_end = shared.ITEM_REF_POS
            f_start_x = f_start * shared.AUDIO_PX_PER_BEAT
            f_end_x = f_end * shared.AUDIO_PX_PER_BEAT
            f_start_line = QGraphicsLineItem(
                f_start_x,
                0.0,
                f_start_x,
                shared.AUDIO_RULER_HEIGHT,
                self.header,
            )
            start_pen = QPen(
                QColor(
                    theme.SYSTEM_COLORS.daw.seq_header_region,
                ),
                6.0,
            )
            f_start_line.setPen(start_pen)
            f_end_line = QGraphicsLineItem(
                f_end_x,
                0.0,
                f_end_x,
                shared.AUDIO_RULER_HEIGHT,
                self.header,
            )
            end_pen = QPen(
                QColor(
                    theme.SYSTEM_COLORS.daw.seq_header_region,
                ),
                6.0,
            )
            f_end_line.setPen(end_pen)
        f_v_pen = QPen(
            QColor(
                theme.SYSTEM_COLORS.daw.seq_bar_line,
            )
        )
        #f_beat_pen = QPen(QColor(210, 210, 210))
        f_16th_pen = QPen(
            QColor(
                theme.SYSTEM_COLORS.daw.seq_16th_line,
            ),
        )
        track_pen = QPen(
            QColor(
                theme.SYSTEM_COLORS.daw.seq_track_line,
            ),
        )
        f_reg_pen = QPen(QtCore.Qt.GlobalColor.white)
        i3 = 0.0
        number_brush = QColor(
            theme.SYSTEM_COLORS.daw.seq_header_text,
        )
        for i in range(int(f_sequence_length)):
            f_number = get_font().QGraphicsSimpleTextItem(
                "{}".format(i + 1),
                self.header,
            )
            f_number.setFlag(
                QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
            )
            f_number.setBrush(number_brush)
            f_number.setZValue(1000.0)
            self.text_list.append(f_number)
            self.scene.addLine(i3, 0.0, i3, self.total_height, f_v_pen)
            f_number.setPos(i3 + 3.0, 2)
            if shared.AUDIO_LINES_ENABLED:
                for f_i4 in range(1, shared.AUDIO_SNAP_RANGE):
                    f_sub_x = i3 + (shared.AUDIO_QUANTIZE_PX * f_i4)
                    f_line = self.scene.addLine(
                        f_sub_x, shared.AUDIO_RULER_HEIGHT,
                        f_sub_x, self.total_height, f_16th_pen)
                    self.beat_line_list.append(f_line)
#            for f_beat_i in range(1, 4):
#                f_beat_x = i3 + (shared.AUDIO_PX_PER_BEAT * f_beat_i)
#                f_line = self.scene.addLine(
#                    f_beat_x, 0.0, f_beat_x, self.total_height, f_beat_pen)
#                self.beat_line_list.append(f_line)
#                if shared.AUDIO_LINES_ENABLED:
#                    for f_i4 in range(1, shared.AUDIO_SNAP_RANGE):
#                        f_sub_x = f_beat_x + (shared.AUDIO_QUANTIZE_PX * f_i4)
#                        f_line = self.scene.addLine(
#                            f_sub_x, shared.AUDIO_RULER_HEIGHT,
#                            f_sub_x, self.total_height, f_16th_pen)
#                        self.beat_line_list.append(f_line)
            i3 += shared.AUDIO_PX_PER_BEAT
        self.scene.addLine(
            i3,
            shared.AUDIO_RULER_HEIGHT,
            i3,
            self.total_height,
            f_reg_pen,
        )
        for i2 in range(shared.AUDIO_ITEM_LANE_COUNT):
            f_y = (
                shared.AUDIO_ITEM_HEIGHT * (i2 + 1)
            ) + shared.AUDIO_RULER_HEIGHT
            self.scene.addLine(0, f_y, f_size, f_y, track_pen)
        self.check_line_count()
        self.set_header_y_pos()

    def clear_drawn_items(self):
        if self.is_playing:
            f_was_playing = True
            self.is_playing = False
        else:
            f_was_playing = False
        self.reset_line_lists()
        self.audio_items = []
        self.scene.clear()
        self.draw_header()
        if f_was_playing:
            self.is_playing = True

    def draw_item(self, a_audio_item_index, a_audio_item, a_graph):
        """a_start in seconds, a_length in seconds"""
        f_audio_item = AudioSeqItem(
            a_audio_item_index,
            a_audio_item,
            a_graph,
        )
        self.audio_items.append(f_audio_item)
        self.scene.addItem(f_audio_item)
        return f_audio_item

class AudioItemSeqWidget(FileDragDropper):
    """ The parent widget (including the file browser dialog) for the
        AudioItemSeq
    """
    def __init__(self):
        FileDragDropper.__init__(self, util.is_audio_file)

        self.papifx = widgets.per_audio_item_fx_widget(
            papifx_rel_callback,
            papifx_val_callback,
        )
        self.papifx_widget = QWidget()
        self.papifx_widget.setObjectName("plugin_ui")
        self.papifx_vlayout = QVBoxLayout(self.papifx_widget)
        fx_text = "Select exactly one item to use"
        self.papifx_stack = QStackedWidget(self.folders_tab_widget)
        self.papifx_stack.addWidget(self.papifx_widget)
        self.papifx_stack.addWidget(QLabel(fx_text))
        self.papifx_stack.setCurrentIndex(1)
        self.folders_tab_widget.addTab(self.papifx_stack, _("File FX"))
        self.papifx.widget.setDisabled(True)
        self.papifx_vlayout.addWidget(self.papifx.scroll_area)

        self.paifx = widgets.per_audio_item_fx_widget(
            paif_rel_callback,
            paif_val_callback,
        )
        self.paifx_widget = QWidget()
        self.paifx_widget.setObjectName("plugin_ui")
        self.paifx_vlayout = QVBoxLayout(self.paifx_widget)
        self.paifx_stack = QStackedWidget(self.folders_tab_widget)
        self.paifx_stack.addWidget(self.paifx_widget)
        self.paifx_stack.addWidget(QLabel(fx_text))
        self.paifx_stack.setCurrentIndex(1)
        self.folders_tab_widget.addTab(self.paifx_stack, _("Item FX"))
        self.paifx.widget.setDisabled(True)
        self.paifx_vlayout.addWidget(self.paifx.scroll_area)

        self.widget = QWidget()
        self.vlayout = QVBoxLayout()
        self.widget.setLayout(self.vlayout)
        self.controls_grid_layout = QGridLayout()
        self.controls_grid_layout.addItem(
            QSpacerItem(10, 10, QSizePolicy.Policy.Expanding),
            0,
            30,
        )
        self.vlayout.addLayout(self.controls_grid_layout)
        self.vlayout.addWidget(shared.AUDIO_SEQ)

        self.menu_button = QPushButton(_("Menu"))
        self.controls_grid_layout.addWidget(self.menu_button, 0, 3)
        self.action_menu = QMenu(self.widget)
        self.menu_button.setMenu(self.action_menu)
        self.copy_action = self.action_menu.addAction(_("Copy"))
        self.copy_action.triggered.connect(self.on_copy)
        self.copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        self.cut_action = self.action_menu.addAction(_("Cut"))
        self.cut_action.triggered.connect(self.on_cut)
        self.cut_action.setShortcut(QKeySequence.StandardKey.Cut)
        self.paste_action = self.action_menu.addAction(_("Paste"))
        self.paste_action.triggered.connect(self.on_paste)
        self.paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        self.select_all_action = self.action_menu.addAction(_("Select All"))
        self.select_all_action.triggered.connect(self.on_select_all)
        self.select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        self.clear_selection_action = self.action_menu.addAction(
            _("Clear Selection"))
        self.clear_selection_action.triggered.connect(
            shared.AUDIO_SEQ.scene.clearSelection)
        self.clear_selection_action.setShortcut(
            QKeySequence.fromString("Esc"))
        self.action_menu.addSeparator()
        self.delete_selected_action = self.action_menu.addAction(_("Delete"))
        self.delete_selected_action.triggered.connect(self.on_delete_selected)
        self.delete_selected_action.setShortcut(
            QKeySequence.StandardKey.Delete,
        )
        self.action_menu.addSeparator()
        self.crossfade_action = self.action_menu.addAction(
            _("Crossfade Selected"))
        self.crossfade_action.triggered.connect(
            shared.AUDIO_SEQ.crossfade_selected,
        )
        self.crossfade_action.setShortcut(
            QKeySequence.fromString("CTRL+F"))

        self.action_menu.addSeparator()
        self.open_last_action = self.action_menu.addAction(
            _("Open Last Item(s)"))
        self.open_last_action.triggered.connect(open_last)
        self.open_last_action.setShortcut(QKeySequence.fromString("ALT+F"))

        self.v_zoom_slider = QSlider(QtCore.Qt.Orientation.Horizontal)
        self.v_zoom_slider.setObjectName("zoom_slider")
        self.v_zoom_slider.setRange(10, 100)
        self.v_zoom_slider.setValue(10)
        self.v_zoom_slider.setSingleStep(1)
        self.v_zoom_slider.setMaximumWidth(150)
        self.v_zoom_slider.valueChanged.connect(self.set_v_zoom)
        self.controls_grid_layout.addWidget(QLabel(_("V")), 0, 45)
        self.controls_grid_layout.addWidget(self.v_zoom_slider, 0, 46)

        self.audio_items_clipboard = []
        self.disable_on_play = (self.menu_button,)
        self.set_multiselect(False)
        self.paifx_clipboard = None

    def on_play(self):
        for f_item in self.disable_on_play:
            f_item.setEnabled(False)

    def on_stop(self):
        for f_item in self.disable_on_play:
            f_item.setEnabled(True)

    def set_tooltips(self, a_on):
        if a_on:
            self.folders_widget.setToolTip(
                sg_strings.audio_viewer_widget_folders,
            )
            self.paifx.widget.setToolTip(
                sg_strings.audio_viewer_widget_paifx,
            )
            self.papifx.widget.setToolTip(
                sg_strings.audio_viewer_widget_papifx,
            )
        else:
            self.folders_widget.setToolTip("")
            self.paifx.widget.setToolTip("")
            self.papifx.widget.setToolTip("")

    def on_select_all(self):
        if (
            shared.CURRENT_SEQUENCE is None
            or
            glbl_shared.IS_PLAYING
        ):
            return
        for f_item in shared.AUDIO_SEQ.audio_items:
            f_item.setSelected(True)

    def on_glue_selected(self):
        if (
            shared.CURRENT_SEQUENCE is None
            or
            glbl_shared.IS_PLAYING
        ):
            return
        shared.AUDIO_SEQ.glue_selected()

    def on_delete_selected(self):
        if (
            shared.CURRENT_SEQUENCE is None
            or
            glbl_shared.IS_PLAYING
        ):
            return
        shared.AUDIO_SEQ.delete_selected()

    def on_papifx_copy(self):
        if _shared.CURRENT_ITEM is not None:
            self.paifx_clipboard = shared.AUDIO_SEQ_WIDGET.papifx.get_list()

    def on_papifx_paste(self):
        if self.paifx_clipboard is not None:
            pool = constants.PROJECT.get_audio_pool()
            uids = set()
            for f_item in shared.AUDIO_SEQ.audio_items:
                if f_item.isSelected():
                    uid = f_item.audio_item.uid,
                    fx = PerFileFX(
                        uid,
                        self.paifx_clipboard,
                    )
                    uids.add(uid)
                    pool.set_per_file_fx(fx)
            constants.PROJECT.save_audio_pool(pool)
            shared.AUDIO_SEQ_WIDGET.papifx.set_from_list(
                self.paifx_clipboard,
            )
            ipc = constants.DAW_PROJECT.ipc()
            for uid in uids:
                fx = PerFileFX(
                    uid,
                    self.paifx_clipboard,
                )
                ipc.audio_per_file_fx_paste(str(fx))


    def on_papifx_clear(self):
        pool = constants.PROJECT.get_audio_pool()
        uids = set()
        for item in shared.AUDIO_SEQ.audio_items:
            if item.isSelected():
                uid = item.audio_item.uid
                pool.remove_per_file_fx(uid)
                uids.add(uid)
        constants.PROJECT.save_audio_pool(pool)
        ipc = constants.DAW_PROJECT.ipc()
        for uid in uids:
            ipc.audio_per_file_fx_clear(uid)
        self.papifx.clear_effects()


    def on_paifx_copy(self):
        if (
            _shared.CURRENT_AUDIO_ITEM_INDEX is not None
            and
            shared.CURRENT_ITEM
        ):
            f_paif = shared.CURRENT_ITEM
            self.paifx_clipboard = f_paif.get_row(
                _shared.CURRENT_AUDIO_ITEM_INDEX,
            )

    def on_paifx_paste(self):
        if (
            self.paifx_clipboard is not None
            and
            shared.CURRENT_ITEM
        ):
            f_paif = shared.CURRENT_ITEM
            for f_item in shared.AUDIO_SEQ.audio_items:
                if f_item.isSelected():
                    f_paif.set_row(
                        f_item.track_num,
                        self.paifx_clipboard,
                    )
            item_lib.save_item(
                shared.CURRENT_ITEM_NAME,
                shared.CURRENT_ITEM,
            )
            shared.AUDIO_SEQ_WIDGET.paifx.set_from_list(
                self.paifx_clipboard,
            )

    def on_paifx_clear(self):
        if shared.CURRENT_ITEM:
            f_paif = shared.CURRENT_ITEM
            for f_item in shared.AUDIO_SEQ.audio_items:
                if f_item.isSelected():
                    f_paif.clear_row_if_exists(f_item.track_num)
            item_lib.save_item(
                shared.CURRENT_ITEM_NAME,
                shared.CURRENT_ITEM,
            )
            self.paifx.clear_effects()

    def on_copy(self):
        if not shared.CURRENT_ITEM or glbl_shared.IS_PLAYING:
            return 0
        self.audio_items_clipboard = []
        f_per_item_fx_dict = shared.CURRENT_ITEM
        f_count = False
        for f_item in shared.AUDIO_SEQ.get_selected():
            f_count = True
            self.audio_items_clipboard.append(
                (str(f_item.audio_item),
                 f_per_item_fx_dict.get_row(f_item.track_num, True)))
        if not f_count:
            QMessageBox.warning(
                self.widget, _("Error"), _("Nothing selected."))
        return f_count

    def on_cut(self):
        if self.on_copy():
            self.on_delete_selected()

    def on_paste(self):
        if not shared.CURRENT_ITEM or glbl_shared.IS_PLAYING:
            return
        if not self.audio_items_clipboard:
            QMessageBox.warning(
                self.widget, _("Error"),
                _("Nothing copied to the clipboard."))
        shared.AUDIO_SEQ.reselect_on_stop = []
        f_per_item_fx_dict = shared.CURRENT_ITEM
#        f_global_tempo = float(TRANSPORT.tempo_spinbox.value())
        for f_str, f_list in self.audio_items_clipboard:
            shared.AUDIO_SEQ.reselect_on_stop.append(f_str)
            f_index = shared.CURRENT_ITEM.get_next_index()
            if f_index == -1:
                break
            f_item = DawAudioItem.from_str(f_str)
            f_start = f_item.start_beat
            if f_start < shared.CURRENT_ITEM_LEN:
#                f_graph = constants.PROJECT.get_sample_graph_by_uid(f_item.uid)
#                f_item.clip_at_sequence_end(
#                    shared.CURRENT_ITEM_LEN, f_global_tempo,
#                    f_graph.length_in_seconds)
                shared.CURRENT_ITEM.add_item(f_index, f_item)
                if f_list is not None:
                    f_per_item_fx_dict.set_row(f_index, f_list)
        shared.CURRENT_ITEM.deduplicate_items()
        item_lib.save_item(
            shared.CURRENT_ITEM_NAME,
            shared.CURRENT_ITEM,
        )
        constants.DAW_PROJECT.commit(_("Paste audio items"))
        global_open_audio_items(True)
        shared.AUDIO_SEQ.scene.clearSelection()
        shared.AUDIO_SEQ.reset_selection()

    def set_v_zoom(self, a_val=None):
        shared.AUDIO_SEQ.set_v_zoom(float(a_val) * 0.1)
        global_open_audio_items(a_reload=False)

def set_audio_seq_zoom(a_horizontal, a_vertical):
    f_width = float(shared.AUDIO_SEQ.rect().width()) - \
        float(shared.AUDIO_SEQ.verticalScrollBar().width()) - 6.0
    f_sequence_length = shared.CURRENT_ITEM_LEN
    f_sequence_px = f_sequence_length * 100.0
    f_sequence_scale = f_width / f_sequence_px

    shared.AUDIO_PX_PER_BEAT = 100.0 * a_horizontal * f_sequence_scale
    shared.AUDIO_SEQ.px_per_beat = shared.AUDIO_PX_PER_BEAT
    set_audio_snap(shared.AUDIO_SNAP_VAL)
    shared.AUDIO_ITEM_HEIGHT = 75.0 * a_vertical
    shared.AUDIO_SEQ.scene.setSceneRect(
        0.0,
        0.0,
        float(shared.AUDIO_PX_PER_BEAT * f_sequence_length),
        float(shared.AUDIO_ITEM_HEIGHT * shared.AUDIO_ITEM_MAX_LANE),
    )

