$(document).ready(function() {
    $('table.jf-pilot').DataTable({
        "order": [[3, "desc"]]
    });
    $('table.jf-pilot-personal').DataTable({
        "order": [[4, "desc"]]
    });
    $('table.datatables').DataTable({
        "lengthMenu": [[20, 50, 75, 100, -1], [20, 50, 75, 100, "All"]]
    });
} );