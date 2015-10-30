$(document).ready(function() {
    $('#jf-personal').DataTable({
        "order": [[4, "desc"]]
    });
    $('#jf-all').DataTable({
        "order": [[5, "desc"]]
    });
    $('table.datatables').DataTable({
        "lengthMenu": [[20, 50, 75, 100, -1], [20, 50, 75, 100, "All"]]
    });
} );