import os
import numpy as np
import tensorflow as tf
from object_detection.utils import label_map_util
from object_detection.utils import visualization_utils as vis_util
import cv2

from src.FPS import FPS

# Define object detection models and labels
PATH_TO_CKPT = 'model/frozen_inference_graph.pb'  # SSD model
PATH_TO_LABELS = 'model/mscoco_label_map.pbtxt'
NUM_CLASSES = 90


class ObjectDetection:
    def __init__(self):
        # Loading label map
        label_map = label_map_util.load_labelmap(PATH_TO_LABELS)
        categories = label_map_util.convert_label_map_to_categories(label_map, max_num_classes=NUM_CLASSES,
                                                                    use_display_name=True)
        self.category_index = label_map_util.create_category_index(categories)

    def detect_objects(self, image_np, sess, detection_graph):
        # Expand dimensions since the model expects images to have shape: [1, None, None, 3]
        image_np_expanded = np.expand_dims(image_np, axis=0)
        image_tensor = detection_graph.get_tensor_by_name('image_tensor:0')

        # Each box represents a part of the image where a particular object was detected.
        boxes = detection_graph.get_tensor_by_name('detection_boxes:0')

        # Each score represent how level of confidence for each of the objects.
        # Score is shown on the result image, together with the class label.
        scores = detection_graph.get_tensor_by_name('detection_scores:0')
        classes = detection_graph.get_tensor_by_name('detection_classes:0')
        num_detections = detection_graph.get_tensor_by_name('num_detections:0')

        # Actual detection.
        (boxes, scores, classes, num_detections) = sess.run(
            [boxes, scores, classes, num_detections],
            feed_dict={image_tensor: image_np_expanded})

        threshold = .5
        objects = []
        for index, value in enumerate(classes[0]):
            object_dict = {}
            if scores[0, index] > threshold:
                object_dict[(self.category_index.get(value)).get('name').encode('utf8')] = scores[0, index]
                objects.append(object_dict)
        print(objects)

        # Visualization of the results of a detection.
        vis_util.visualize_boxes_and_labels_on_image_array(
            image_np,
            np.squeeze(boxes),
            np.squeeze(classes).astype(np.int32),
            np.squeeze(scores),
            self.category_index,
            use_normalized_coordinates=True,
            line_thickness=4)

        return image_np

    def worker(self, input_q, output_q):
        # Load a (frozen) Tensorflow model into memory.
        detection_graph = tf.Graph()
        with detection_graph.as_default():
            od_graph_def = tf.GraphDef()
            with tf.gfile.GFile(PATH_TO_CKPT, 'rb') as fid:
                serialized_graph = fid.read()
                od_graph_def.ParseFromString(serialized_graph)
                with tf.device('/gpu:0'):
                    tf.import_graph_def(od_graph_def, name='')

            config = tf.ConfigProto(allow_soft_placement=True, log_device_placement=False)
            config.gpu_options.allow_growth = True
            sess = tf.Session(graph=detection_graph, config=config)

        fps = FPS().start()

        while True:
            fps.update()
            frame = input_q.get()
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            output_q.put(self.detect_objects(frame_rgb, sess, detection_graph))

        fps.stop()
        sess.close()
