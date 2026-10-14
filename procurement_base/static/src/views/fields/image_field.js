import { patch } from "@web/core/utils/patch";
import { ImageField } from "@web/views/fields/image/image_field";
import { useFileViewer } from "@web/core/file_viewer/file_viewer_hook";

patch(ImageField.prototype, {
    setup() {
        super.setup();
        this.fileViewer = useFileViewer();
    },

    onImageClick(ev) {
        if (!this.hasTooltip && !this.props.enableZoom) {
            return;
        }
        if (!this.props.record.data[this.props.name]) {
            return;
        }
        ev.stopPropagation();
        ev.preventDefault();

        const fieldName = this.fieldType === "many2one" ? this.props.previewImage : this.props.name;
        const url = this.getUrl(fieldName);
        const name = this.imgAlt || "Product Image";

        this.fileViewer.open({
            isImage: true,
            isViewable: true,
            name: name,
            defaultSource: url,
            downloadUrl: url,
        });
    },
});
