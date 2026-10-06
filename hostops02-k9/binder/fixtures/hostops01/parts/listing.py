MAX_LISTING_ROWS=64
# Typed fields only. Never run by this family on this host before OP_PRECHECK; whether the ID printed here equals the
# inspect ID under the containerd image store is unverified, which is why a listing without the signed ID proves nothing.
LS_FORMAT='{"id":{{json .ID}},"repository":{{json .Repository}},"tag":{{json .Tag}}}'

def listing(commands):
    """docker image ls of the one repository: rows of (id, repository, tag). A failed listing is never an absence."""
    try:raw=commands.output('image_ls')
    except Refused as error:
        raise Refused(str(error) if str(error) in ('GO_EXPIRED','CLOCK_REVERSED','BINARY_UNAVAILABLE_OR_UNSAFE') else 'TAG_LISTING_UNAVAILABLE') from None
    rows=[]
    try:
        for line in raw.splitlines():
            if not line:continue
            row=decode(line)
            need(set(row)=={'id','repository','tag'} and text(row['id'],IMAGE_ID) and row['repository']==REPOSITORY
                 and text(row['tag'],'[A-Za-z0-9_.<>-]{1,128}'),'TAG_LISTING_UNAVAILABLE')
            rows.append(row);need(len(rows)<=MAX_LISTING_ROWS,'TAG_LISTING_UNAVAILABLE')
    except Refused:raise Refused('TAG_LISTING_UNAVAILABLE') from None
    return rows
