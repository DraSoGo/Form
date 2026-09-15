# NAS actions

No new TrueNAS dataset or existing application dataset change is required. The existing mounted share `/mnt/nas-backup` (`//192.168.1.38/server-backup`) is sufficient. Fitness creates only its own `Fitness/` directory with `snapshots/` and content-addressed `blobs/` below it.

The backup operator needs read/write access within that directory. Existing CIFS ownership/mode settings and share ACLs govern effective access; hardlinks and Unix mode support are not required. Verify the share mount and free space before enabling the timer. Backup fails closed if the expected mount is absent. Do not create a plain local substitute for the mount.

Restrict NAS share access because snapshots contain health records/photos and database sessions. Optional NAS-level snapshots/encryption must follow the owner's existing policy; this deployment does not change NAS services or sibling application data.
