
import cv2 as _cv2

# OpenCL off: ORB on OpenCL takes the Intel GPU, and Windows then refuses screen duplication
# to the whole process ("device interface or feature level is not supported", 11 Nov 2026).
_cv2.ocl.setUseOpenCL(False)
