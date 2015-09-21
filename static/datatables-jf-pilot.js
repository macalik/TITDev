$(document).ready(function() {
    $('table.jf-pilot').DataTable({
        "order": [[3, "desc"]]
    });
    $('table.jf-pilot-personal').DataTable({
        "order": [[4, "desc"]]
    });
} );