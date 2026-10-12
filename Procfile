# 2 workers x 4 threads keeps thumbnail bursts (an admin page issues many
# /media/ requests at once) from piling up behind one synchronous worker.
# The generous timeout matters on a small instance talking to a remote
# database: gunicorn's default 30s was aborting workers mid-query, which the
# logs showed as "WORKER TIMEOUT" / "handle_abort" / SIGKILL and the admin
# product page as "Internal Server Error".
web: gunicorn ecommerce.wsgi --workers 2 --threads 4 --timeout 60 --graceful-timeout 30 --log-file -
